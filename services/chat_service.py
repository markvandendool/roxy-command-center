#!/usr/bin/env python3
"""
Chat Service - canonical ROXY harness adapter.

DOCTRINE:
- GTK app stays thin client
- Owner-facing chat goes through roxy-chat-proxy :4001
- Raw Ollama, LiteLLM, and Ada endpoints are never called by this client

Endpoints used:
- GET /health
- POST /v1/chat/completions
"""

import gi
gi.require_version('Soup', '3.0')
from gi.repository import GLib, Soup, Gio
import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

from services.operator_kernel_client import get_source_commit


# =============================================================================
# CONFIGURATION
# =============================================================================

ROXY_CHAT_PROXY_URL = os.getenv("ROXY_CHAT_PROXY_URL", "http://127.0.0.1:4001").rstrip("/")
DEFAULT_MODEL = os.getenv("ROXY_COMMAND_CENTER_MODEL", "roxy-coder-frontier")
CHAT_RECEIPT_DIR = Path.home() / ".cache" / "roxy-command-center" / "chat-receipts"
LANE_MODELS = {
    "auto": "roxy-coder-frontier",
    "frontier": "roxy-coder-frontier",
    "judge": "roxy-cpu-supermodel",
    "local": "roxy-chat",
    "cloud": "roxy-smart",
}


def build_harness_payload(
    messages: List[Dict[str, str]],
    model: str,
    session_id: Optional[str] = None,
    routing_mode: str = "",
) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 2048,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if session_id:
        payload["session_id"] = session_id
    if routing_mode and routing_mode != "AUTO":
        payload["roxy_route_mode"] = routing_mode
    return payload


def validate_harness_response(data: dict, expected_model: str) -> dict:
    """Reject successful-looking responses that do not prove the requested lane."""
    data = data if isinstance(data, dict) else {}
    roxy = data.get("roxy") if isinstance(data.get("roxy"), dict) else {}
    route = roxy.get("routeDecision") if isinstance(roxy.get("routeDecision"), dict) else {}
    choices = data.get("choices") if isinstance(data.get("choices"), list) else []
    message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
    content = message.get("content", "") if isinstance(message, dict) else ""
    finish_reason = choices[0].get("finish_reason") if choices and isinstance(choices[0], dict) else None
    timings = data.get("timings") if isinstance(data.get("timings"), dict) else {}

    failures = []
    actual_model = data.get("model")
    if actual_model != expected_model:
        failures.append(f"model={actual_model!r} expected={expected_model!r}")
    if route.get("originalModel") != expected_model:
        failures.append(f"originalModel={route.get('originalModel')!r}")
    if route.get("selectedModel") != expected_model:
        failures.append(f"selectedModel={route.get('selectedModel')!r}")
    if route.get("rerouted") is not False:
        failures.append(f"rerouted={route.get('rerouted')!r}")
    if roxy.get("degradedFallback") is True:
        failures.append("degradedFallback=true")
    if roxy.get("harnessBypassDetected") is not False:
        failures.append(f"harnessBypassDetected={roxy.get('harnessBypassDetected')!r}")
    if roxy.get("harnessEnforced") is not False:
        failures.append(f"harnessEnforced={roxy.get('harnessEnforced')!r}")
    if not roxy.get("sessionId"):
        failures.append("sessionId missing")
    if roxy.get("persistenceStatus") != "live":
        failures.append(f"persistenceStatus={roxy.get('persistenceStatus')!r}")
    if roxy.get("memoryStatus") != "persisted":
        failures.append(f"memoryStatus={roxy.get('memoryStatus')!r}")
    if roxy.get("identityCapsuleApplied") is not True:
        failures.append(f"identityCapsuleApplied={roxy.get('identityCapsuleApplied')!r}")
    if finish_reason != "stop":
        failures.append(f"finish_reason={finish_reason!r}")
    predicted_ms = timings.get("predicted_ms")
    if not isinstance(predicted_ms, (int, float)) or predicted_ms <= 0:
        failures.append("backend timings missing")
    if not str(content).strip():
        failures.append("assistant content empty")

    return {
        "ok": not failures,
        "failures": failures,
        "content": str(content),
        "model": actual_model,
        "sessionId": roxy.get("sessionId"),
        "persistenceStatus": roxy.get("persistenceStatus"),
        "routeDecision": route,
        "finishReason": finish_reason,
        "timings": timings,
        "memoryStatus": roxy.get("memoryStatus"),
        "identityCapsuleApplied": roxy.get("identityCapsuleApplied"),
        "harnessEnforced": roxy.get("harnessEnforced"),
        "providerExecuted": isinstance(predicted_ms, (int, float)) and predicted_ms > 0,
        "usage": data.get("usage") if isinstance(data.get("usage"), dict) else {},
    }


def write_chat_receipt(receipt: dict) -> Path:
    """Persist one validated native response atomically with private permissions."""
    CHAT_RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S.%f")
    path = CHAT_RECEIPT_DIR / f"rcc-chat-{stamp}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return path


# =============================================================================
# DATA MODELS
# =============================================================================

class Identity(Enum):
    """User identity for routing."""
    ME = "me"
    MINDSONG = "mindsong"


class ChatMode(Enum):
    """Chat mode - human-in-the-loop control."""
    DRAFT = "draft"      # Roxy suggests, user approves
    SEND = "send"        # Roxy executes directly (requires explicit arming)


class ConnectionStatus(Enum):
    """Connection state to the ROXY harness."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    WARMING = "warming"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ChatMessage:
    """A message in the conversation."""
    id: str
    role: str           # "user", "assistant", "system"
    content: str
    timestamp: datetime
    identity: Identity = Identity.MINDSONG
    pending: bool = False  # True while waiting for response
    latency_ms: int = 0
    model: str = ""
    route_decision: Dict[str, Any] = field(default_factory=dict)
    persistence_status: str = ""
    session_id: str = ""
    provider_timings: Dict[str, Any] = field(default_factory=dict)
    degraded_fallback: bool = False
    harness_bypassed: bool = False
    receipt_path: str = ""


@dataclass
class ChatSession:
    """A chat session with current ROXY."""
    id: str
    identity: Identity
    mode: ChatMode
    messages: List[ChatMessage]
    created_at: datetime
    model: str = "unknown"
    roxy_session_id: Optional[str] = None
    

# =============================================================================
# CHAT SERVICE
# =============================================================================

class ChatService:
    """
    Service for communicating with current ROXY through its harness.
    
    Responsibilities:
    - Send owner-facing messages to roxy-chat-proxy
    - Manage session state
    - Notify UI of responses (via callbacks)
    - Handle connection status
    
    Does NOT:
    - Process LLM directly
    - Handle STT/TTS directly
    - Render UI
    """
    
    def __init__(self):
        self._session: Optional[ChatSession] = None
        self._soup_session = Soup.Session()
        try:
            self._soup_session.set_property("timeout", 120)
        except TypeError:
            try:
                self._soup_session.props.timeout = 120
            except Exception:
                pass
        except Exception:
            pass
        self._status = ConnectionStatus.DISCONNECTED
        self._timeout_handles: List[int] = []
        self._pending_request_active = False
        self._pending_message: Optional[Soup.Message] = None
        self._timeout_error_triggered = False
        self._last_error_message: Optional[str] = None
        self._proxy_base_url: str = ROXY_CHAT_PROXY_URL
        self._selected_lane: str = "auto"
        self._requested_model: str = DEFAULT_MODEL
        
        # Callbacks
        self._on_message: Optional[Callable[[ChatMessage], None]] = None
        self._on_status_change: Optional[Callable[[ConnectionStatus, str], None]] = None
        self._on_typing: Optional[Callable[[bool], None]] = None
        
        # Metadata from last response
        self._last_model: str = "unknown"
        self._last_expert: str = "roxy"
        self._last_latency_ms: int = 0
        
        # Execution metadata (Chief's Truth Panel)
        self._last_execution_meta: dict = {}
        self._on_meta_update: Optional[Callable[[dict], None]] = None
    
    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    
    def connect(
        self,
        identity: Identity = Identity.MINDSONG,
        on_message: Optional[Callable[[ChatMessage], None]] = None,
        on_status_change: Optional[Callable[[ConnectionStatus, str], None]] = None,
        on_typing: Optional[Callable[[bool], None]] = None,
        on_meta_update: Optional[Callable[[dict], None]] = None
    ):
        """
        Connect to the ROXY harness and create a session.
        
        Args:
            identity: Which identity to use (me vs mindsong)
            on_message: Callback when new message arrives
            on_status_change: Callback when connection status changes
            on_typing: Callback when typing indicator should show/hide
            on_meta_update: Callback when execution metadata updates
        """
        self._on_message = on_message
        self._on_status_change = on_status_change
        self._on_typing = on_typing
        self._on_meta_update = on_meta_update
        
        # Create new session
        self._session = ChatSession(
            id=str(uuid.uuid4()),
            identity=identity,
            mode=ChatMode.DRAFT,
            messages=[],
            created_at=datetime.now()
        )
        
        # Test the canonical harness and its upstream reachability.
        self._set_status(ConnectionStatus.CONNECTING, "Connecting to ROXY harness...")
        self._ping_roxy_core()
    
    def disconnect(self):
        """Disconnect from the ROXY harness."""
        self._session = None
        self._set_status(ConnectionStatus.DISCONNECTED, "Disconnected")
    
    def send_message(self, text: str, routing_mode: str = "", pool: str = "") -> Optional[ChatMessage]:
        """
        Send a message to Roxy and get a response.

        Args:
            text: The user's message
            routing_mode: Explicit routing mode (CHAT/RAG/EXEC) - empty means auto
            pool: Explicit pool, currently ignored unless ROXY/AUTO

        Returns:
            The user message (assistant response comes via callback)
        """
        if not self._session:
            print("[ChatService] No session, cannot send")
            return None
        
        if not text.strip():
            return None

        if self._pending_request_active:
            if self._on_message:
                self._on_message(
                    ChatMessage(
                        id=str(uuid.uuid4()),
                        role="system",
                        content="RCC_CHAT_REQUEST_ALREADY_ACTIVE",
                        timestamp=datetime.now(),
                    )
                )
            return None
        
        # Create user message
        user_msg = ChatMessage(
            id=str(uuid.uuid4()),
            role="user",
            content=text,
            timestamp=datetime.now(),
            identity=self._session.identity
        )
        self._session.messages.append(user_msg)
        
        # Notify UI
        if self._on_message:
            self._on_message(user_msg)
        
        # Show typing indicator
        if self._on_typing:
            self._on_typing(True)
        
        # Send through the ROXY harness with operator controls.
        self._send_to_roxy_core(text, routing_mode=routing_mode, pool=pool)
        
        return user_msg
    
    def set_mode(self, mode: ChatMode):
        """Set chat mode (draft vs send)."""
        if self._session:
            self._session.mode = mode
            print(f"[ChatService] Mode set to {mode.value}")
    
    def set_identity(self, identity: Identity):
        """Switch identity."""
        if self._session:
            self._session.identity = identity
            print(f"[ChatService] Identity set to {identity.value}")
    
    @property
    def status(self) -> ConnectionStatus:
        return self._status
    
    @property
    def session(self) -> Optional[ChatSession]:
        return self._session
    
    @property
    def model(self) -> str:
        return self._last_model
    
    @property
    def expert(self) -> str:
        return self._last_expert
    
    @property
    def latency_ms(self) -> int:
        return self._last_latency_ms

    def set_lane(self, lane: str):
        lane = str(lane or "auto").lower()
        self._selected_lane = lane if lane in LANE_MODELS else "auto"
        print(f"[ChatService] Lane set to {self._selected_lane} -> {LANE_MODELS[self._selected_lane]}")

    @property
    def selected_lane(self) -> str:
        return self._selected_lane

    def _resolve_model(self) -> str:
        return LANE_MODELS.get(self._selected_lane, DEFAULT_MODEL)
    
    # -------------------------------------------------------------------------
    # Internal: canonical ROXY harness communication
    # -------------------------------------------------------------------------
    
    def _ping_roxy_core(self, retry_count: int = 0):
        """Test connection to roxy-chat-proxy via /health.
        
        Args:
            retry_count: Current retry attempt (max 2 retries on timeout)
        """
        uri = f"{self._proxy_base_url}/health"
        message = Soup.Message.new("GET", uri)

        self._soup_session.send_async(message, GLib.PRIORITY_DEFAULT, None, self._on_ping_response, retry_count)
    
    def _on_ping_response(self, session, result, retry_count):
        """Handle ping response from /health."""
        retry_count = retry_count if isinstance(retry_count, int) else 0
        try:
            input_stream = session.send_finish(result)
            
            # Read response
            data_stream = Gio.DataInputStream.new(input_stream)
            lines = []
            while True:
                line, length = data_stream.read_line_utf8(None)
                if line is None:
                    break
                lines.append(line)
            
            data = "".join(lines)
            
            if data:
                try:
                    status = json.loads(data)
                    proxy_ok = status.get("ok") is True
                    upstream_ok = status.get("upstreamReachable") is True
                    status_state = ConnectionStatus.CONNECTED if proxy_ok and upstream_ok else ConnectionStatus.ERROR
                    self._last_model = self._resolve_model()
                    status_message = (
                        f"ROXY harness ready at {self._proxy_base_url} -> {self._last_model}"
                        if status_state == ConnectionStatus.CONNECTED
                        else f"ROXY harness degraded: proxy={proxy_ok} upstream={upstream_ok}"
                    )

                    if status_state != ConnectionStatus.ERROR:
                        self._last_error_message = None
                    self._set_status(status_state, status_message)

                    if self._session and self._on_message:
                        prefix = "✅" if status_state == ConnectionStatus.CONNECTED else "⚠️"
                        sys_msg = ChatMessage(
                            id=str(uuid.uuid4()),
                            role="system",
                            content=f"{prefix} {status_message}",
                            timestamp=datetime.now()
                        )
                        self._on_message(sys_msg)
                except json.JSONDecodeError as exc:
                    self._set_status(ConnectionStatus.ERROR, f"Invalid harness health JSON: {exc}")
            else:
                self._set_status(ConnectionStatus.ERROR, "ROXY harness health returned no data")
                
        except Exception as e:
            error_str = str(e)
            is_timeout = "timed out" in error_str.lower() or "timeout" in error_str.lower()
            
            # Retry up to 2 times on timeout errors
            if is_timeout and retry_count < 2:
                print(f"[ChatService] Ping timeout, retry {retry_count + 1}/2...")
                GLib.timeout_add_seconds(1, lambda: self._ping_roxy_core(retry_count + 1) or False)
                return
            
            print(f"[ChatService] Ping failed: {e}")
            self._set_status(ConnectionStatus.ERROR, f"Connection failed: {e}")
    
    def _send_to_roxy_core(self, text: str, routing_mode: str = "", pool: str = ""):
        """Send a message through roxy-chat-proxy /v1/chat/completions.

        Args:
            text: The message to send
            routing_mode: Explicit ROXY operator route mode
            pool: UI lane label for receipt metadata
        """
        uri = f"{self._proxy_base_url}/v1/chat/completions"
        message = Soup.Message.new("POST", uri)
        
        # Set headers
        headers = message.get_request_headers()
        headers.append("Content-Type", "application/json")
        model = self._resolve_model()
        self._requested_model = model
        messages = [
            {"role": item.role, "content": item.content}
            for item in (self._session.messages if self._session else [])
            if item.role in ("user", "assistant")
        ]
        payload = build_harness_payload(
            messages or [{"role": "user", "content": text}],
            model,
            self._session.roxy_session_id if self._session else None,
            routing_mode,
        )
        if self._session and self._session.roxy_session_id:
            headers.append("x-roxy-session-id", self._session.roxy_session_id)
        
        # Set body
        body_bytes = json.dumps(payload).encode('utf-8')
        message.set_request_body_from_bytes("application/json", GLib.Bytes.new(body_bytes))
        
        # Record start time for latency
        start_time = GLib.get_monotonic_time()
        
        # Store start_time as instance var since user_data doesn't work reliably
        self._request_start_time = start_time
        self._active_request = {
            "model": model,
            "lane": self._selected_lane,
            "routeMode": routing_mode or "AUTO",
            "pool": pool or self._selected_lane.upper(),
            "prompt": text,
        }
        self._pending_request_active = True
        self._timeout_error_triggered = False
        self._last_error_message = None
        self._cancel_status_timeouts()
        self._set_status(ConnectionStatus.CONNECTING, "Sending…")
        self._pending_message = message
        
        print(f"[ChatService] Sending to {uri} model={model}...")
        
        # Send async
        self._soup_session.send_async(
            message, 
            GLib.PRIORITY_DEFAULT, 
            None, 
            self._on_run_response, 
            None  # user_data - not reliably passed in all libsoup versions
        )
        self._schedule_status_updates()
    
    def _cancel_status_timeouts(self):
        for handle in self._timeout_handles:
            GLib.source_remove(handle)
        self._timeout_handles.clear()

    def _schedule_status_updates(self):
        self._cancel_status_timeouts()
        self._timeout_handles.append(
            GLib.timeout_add_seconds(5, self._status_callback(
                ConnectionStatus.WARMING,
                "Loading model… (cold start can take 60–120s)"
            ))
        )
        self._timeout_handles.append(
            GLib.timeout_add_seconds(30, self._status_callback(
                ConnectionStatus.WARMING,
                "Still loading…"
            ))
        )
        self._timeout_handles.append(
            GLib.timeout_add_seconds(120, self._timeout_callback())
        )

    def _status_callback(self, status: ConnectionStatus, message: str):
        def _callback():
            if not self._pending_request_active:
                return False
            self._set_status(status, message)
            return False
        return _callback

    def _timeout_callback(self):
        def _callback():
            if not self._pending_request_active:
                return False
            host = self._proxy_base_url or ROXY_CHAT_PROXY_URL
            message = f"Timed out waiting for first token. Check ROXY harness at {host}/health"
            self._timeout_error_triggered = True
            self._pending_request_active = False
            if self._pending_message is not None:
                try:
                    self._soup_session.cancel_message(self._pending_message, Soup.Status.CANCELLED)
                except Exception:
                    pass
                self._pending_message = None
            self._handle_error(message)
            return False
        return _callback

    def _on_run_response(self, session, result, user_data):
        """Handle and validate /v1/chat/completions from roxy-chat-proxy."""
        print("[ChatService] Response callback triggered")
        self._cancel_status_timeouts()
        self._pending_request_active = False
        self._pending_message = None
        self._timeout_error_triggered = False
        request_context = dict(getattr(self, "_active_request", {}))
        self._active_request = {}
        
        # Hide typing indicator
        if self._on_typing:
            self._on_typing(False)
        
        try:
            input_stream = session.send_finish(result)
            
            # Calculate latency using stored start time
            end_time = GLib.get_monotonic_time()
            start_time = getattr(self, '_request_start_time', end_time)
            self._last_latency_ms = int((end_time - start_time) / 1000)
            print(f"[ChatService] Latency: {self._last_latency_ms}ms")
            
            # Read full response
            data_stream = Gio.DataInputStream.new(input_stream)
            lines = []
            while True:
                line, length = data_stream.read_line_utf8(None)
                if line is None:
                    break
                lines.append(line)
            
            response_text = "\n".join(lines)
            
            if not response_text:
                self._handle_error("No response from ROXY harness")
                return

            try:
                data = json.loads(response_text)
            except json.JSONDecodeError as exc:
                self._handle_error(f"Invalid ROXY harness JSON: {exc}")
                return

            if data.get("error") and not data.get("choices"):
                error = data["error"]
                if isinstance(error, dict):
                    error = error.get("message") or json.dumps(error)
                self._handle_error(f"ROXY harness error: {error}")
                return

            expected_model = request_context.get("model") or self._requested_model
            validated = validate_harness_response(data, expected_model)
            if not validated["ok"]:
                self._handle_error(
                    "RCC_ADA_ROUTE_INTEGRITY_FAILED: " + "; ".join(validated["failures"])
                )
                return

            self._last_model = validated["model"]
            self._last_expert = "roxy-harness"
            if self._session:
                self._session.roxy_session_id = validated["sessionId"]

            route = validated["routeDecision"]
            chat_receipt = {
                "schemaVersion": "rcc-native-chat-receipt.v1",
                "generatedAt": datetime.now().isoformat(),
                "sourceCommit": get_source_commit(),
                "integrity": {"ok": True, "failures": []},
                "request": {
                    "prompt": request_context.get("prompt"),
                    "model": expected_model,
                    "lane": request_context.get("lane"),
                    "routeMode": request_context.get("routeMode"),
                },
                "response": {
                    "content": validated["content"],
                    "model": validated["model"],
                    "sessionId": validated["sessionId"],
                    "persistenceStatus": validated["persistenceStatus"],
                    "memoryStatus": validated["memoryStatus"],
                    "routeDecision": route,
                    "clientLatencyMs": self._last_latency_ms,
                    "providerTimings": validated["timings"],
                    "usage": validated["usage"],
                    "degradedFallback": False,
                    "harnessBypassDetected": False,
                },
            }
            receipt_path = write_chat_receipt(chat_receipt)
            meta = {
                "mode": "ROXY",
                "pool": request_context.get("pool", "AUTO"),
                "route": f"harness/{request_context.get('lane', 'unknown')}",
                "model_used": self._last_model,
                "requested_model": expected_model,
                "selected_model": route.get("selectedModel"),
                "rerouted": route.get("rerouted"),
                "degraded_fallback": False,
                "harness_bypassed": False,
                "total_ms": self._last_latency_ms,
                "session_id": validated["sessionId"],
                "persistence_status": validated["persistenceStatus"],
                "memory_status": validated["memoryStatus"],
                "identity_capsule_applied": validated["identityCapsuleApplied"],
                "harness_enforced": validated["harnessEnforced"],
                "finish_reason": validated["finishReason"],
                "backend_timings": validated["timings"],
                "provider_executed": validated["providerExecuted"],
                "usage": validated["usage"],
                "receipt_path": str(receipt_path),
            }
            self._last_execution_meta = meta
            if self._on_meta_update:
                self._on_meta_update(meta)

            assistant_msg = ChatMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                content=validated["content"],
                timestamp=datetime.now(),
                identity=self._session.identity if self._session else Identity.MINDSONG,
                latency_ms=self._last_latency_ms,
                model=self._last_model,
                route_decision=route,
                persistence_status=validated["persistenceStatus"],
                session_id=validated["sessionId"],
                provider_timings=validated["timings"],
                degraded_fallback=False,
                harness_bypassed=False,
                receipt_path=str(receipt_path),
            )
            if self._session:
                self._session.messages.append(assistant_msg)
            if self._on_message:
                self._on_message(assistant_msg)
            self._set_status(
                ConnectionStatus.CONNECTED,
                f"Ada verified via ROXY harness in {self._last_latency_ms}ms",
            )
            self._last_error_message = None
                
        except Exception as e:
            print(f"[ChatService] Error: {e}")
            self._handle_error(str(e))
    
    def _handle_error(self, error: str):
        """Handle error response."""
        self._cancel_status_timeouts()
        self._pending_request_active = False
        self._pending_message = None
        self._active_request = {}
        if self._on_typing:
            self._on_typing(False)
        self._set_status(ConnectionStatus.ERROR, error)
        if error == self._last_error_message:
            return
        self._last_error_message = error
        if self._on_message:
            error_msg = ChatMessage(
                id=str(uuid.uuid4()),
                role="system",
                content=f"⚠️ {error}",
                timestamp=datetime.now()
            )
            self._on_message(error_msg)
    
    def _set_status(self, status: ConnectionStatus, message: str):
        """Update connection status."""
        self._status = status
        print(f"[ChatService] Status: {status.value} - {message}")
        if self._on_status_change:
            self._on_status_change(status, message)


# =============================================================================
# VOICE SERVICE (Stub for Phase 2)
# =============================================================================

class VoiceService:
    """
    Service for future voice input/output.
    
    Phase 1: Stub
    Phase 2: Push-to-talk → STT → Chat → TTS → Playback
    
    Endpoints to be implemented in a future local API:
    - POST /api/voice/transcribe - Audio → Text
    - POST /api/voice/speak - Text → Audio
    """
    
    def __init__(self, chat_service: ChatService):
        self._chat = chat_service
        self._is_recording = False
        self._speak_mode = False  # Option B: speak button, not auto-speak
        
        # Callbacks
        self._on_recording_change: Optional[Callable[[bool], None]] = None
        self._on_audio_play: Optional[Callable[[bytes], None]] = None
    
    @property
    def is_recording(self) -> bool:
        return self._is_recording
    
    @property
    def speak_mode(self) -> bool:
        return self._speak_mode
    
    @speak_mode.setter
    def speak_mode(self, value: bool):
        """Toggle speak mode (Option B: manual button)."""
        self._speak_mode = value
        print(f"[VoiceService] Speak mode: {value}")
    
    def start_recording(self):
        """Start recording (push-to-talk pressed)."""
        # TODO: Phase 2 - Start microphone capture
        self._is_recording = True
        print("[VoiceService] Recording started (stub)")
        if self._on_recording_change:
            self._on_recording_change(True)
    
    def stop_recording(self):
        """Stop recording and transcribe."""
        # TODO: Phase 2 - Stop capture, send to /api/voice/transcribe
        self._is_recording = False
        print("[VoiceService] Recording stopped (stub)")
        if self._on_recording_change:
            self._on_recording_change(False)
        
        # Stub: simulate transcription result
        # In Phase 2, this would call a local transcription endpoint
        # then auto-submit to chat_service.send_message(transcript)
    
    def speak(self, text: str):
        """Request TTS for text (Option B: manual speak button)."""
        if not self._speak_mode:
            print("[VoiceService] Speak mode disabled")
            return
        
        # TODO: Phase 2 - Call /api/voice/speak endpoint
        print(f"[VoiceService] Speak request (stub): {text[:50]}...")
        
        # In Phase 2:
        # 1. POST /api/voice/speak with text
        # 2. Get audio bytes back
        # 3. Call self._on_audio_play(audio_bytes)
    
    def set_callbacks(
        self,
        on_recording_change: Optional[Callable[[bool], None]] = None,
        on_audio_play: Optional[Callable[[bytes], None]] = None
    ):
        """Set callbacks for voice events."""
        self._on_recording_change = on_recording_change
        self._on_audio_play = on_audio_play


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_chat_service: Optional[ChatService] = None
_voice_service: Optional[VoiceService] = None


def get_chat_service() -> ChatService:
    """Get or create the global chat service."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service


def get_voice_service() -> VoiceService:
    """Get or create the global voice service."""
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService(get_chat_service())
    return _voice_service
