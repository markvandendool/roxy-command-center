#!/usr/bin/env python3
"""
Chat Service — Canonical ROXY Harness Adapter.

DOCTRINE:
- GTK app stays thin client
- ALL owner-facing chat goes through roxy-chat-proxy :4001
- Never call raw Qwen, never call raw LiteLLM, never call Ollama /api/generate directly

Canonical path:
  GTK4 Roxy Command Center
  → POST http://127.0.0.1:4001/v1/chat/completions
  → roxy-chat-proxy.mjs (:4001)
  → config/roxy/roxy-brain-system-prompt.md
  → skill embeddings
  → SQLite memory
  → Qdrant/RAG/context
  → LiteLLM :4000
  → Qwen 3.6 MTP :8085

Endpoints used:
- GET  /health           — proxy health + upstream reachability
- POST /v1/chat/completions — canonical chat with RAG/memory/context
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


# =============================================================================
# CONFIGURATION
# =============================================================================

ROXY_CHAT_PROXY_URL = os.getenv("ROXY_CHAT_PROXY_URL", "http://127.0.0.1:4001").rstrip("/")
DEFAULT_MODEL = os.getenv("ROXY_COMMAND_CENTER_MODEL", "roxy-coder-frontier")

# Session persistence — no localStorage in GTK; use canonical JSON file
SESSION_PATH = Path.home() / ".config" / "roxy-command-center" / "chat-session.json"


# =============================================================================
# DATA MODELS
# =============================================================================

class Identity(Enum):
    """User identity for routing."""
    ME = "me"
    MINDSONG = "mindsong"


class ChatMode(Enum):
    """Chat mode — human-in-the-loop control."""
    DRAFT = "draft"      # Roxy suggests, user approves
    SEND = "send"        # Roxy executes directly (requires explicit arming)


class ConnectionStatus(Enum):
    """Connection state to ROXY harness."""
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
    # Roxy harness metadata (populated on assistant messages)
    latency_ms: int = 0
    model: str = ""
    memory_refs: List[str] = field(default_factory=list)
    proposed_actions: List[str] = field(default_factory=list)
    # Context Inspector metadata (JARVIS Context Kernel)
    context_hash: str = ""
    context_kernel_version: str = ""
    source_health: Dict[str, Any] = field(default_factory=dict)
    token_budget: Dict[str, Any] = field(default_factory=dict)
    orico_counts: Dict[str, Any] = field(default_factory=dict)
    degraded_reasons: List[str] = field(default_factory=list)
    harness_bypassed: bool = False


@dataclass
class ChatSession:
    """A chat session with current ROXY."""
    id: str
    identity: Identity
    mode: ChatMode
    messages: List[ChatMessage]
    created_at: datetime
    model: str = "unknown"
    # Harness-level session id (from roxy-chat-proxy SQLite store)
    roxy_session_id: Optional[str] = None


# =============================================================================
# SESSION PERSISTENCE
# =============================================================================

# =============================================================================
# SESSION PERSISTENCE — Phase 4: Save-authority UX
# =============================================================================

MAX_BACKUPS = 5


def _rotate_backups():
    """Rotate session backups, keeping MAX_BACKUPS most recent."""
    try:
        parent = SESSION_PATH.parent
        backups = sorted(parent.glob("chat-session.json.*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[MAX_BACKUPS:]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def _atomic_write(path: Path, data: str):
    """Atomic write: temp file + rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def _load_session_state() -> Dict[str, Any]:
    """Load persisted session state from disk (session id + conversation history)."""
    try:
        if SESSION_PATH.exists():
            return json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ChatService] Session load error: {e}")
    return {}


def _save_session_state(state: Dict[str, Any]) -> None:
    """Save session state to disk with atomic write and backup rotation."""
    try:
        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Backup existing file before overwrite
        if SESSION_PATH.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = SESSION_PATH.with_suffix(f".json.{ts}.bak")
            SESSION_PATH.rename(backup)
            _rotate_backups()
        _atomic_write(SESSION_PATH, json.dumps(state, indent=2, default=str))
    except Exception as e:
        print(f"[ChatService] Session save error: {e}")


def _export_session_to_markdown(messages: List[ChatMessage], path: Path) -> bool:
    """Export conversation history to markdown file."""
    try:
        lines = ["# Roxy Conversation Export\n"]
        lines.append(f"**Exported:** {datetime.now().isoformat()}\n")
        lines.append(f"**Messages:** {len(messages)}\n\n---\n\n")
        for m in messages:
            role = "🧑 User" if m.role == "user" else "🤖 Roxy"
            lines.append(f"## {role} — {m.timestamp.isoformat()}\n")
            lines.append(f"{m.content}\n")
            if m.model:
                lines.append(f"\n*Model: {m.model} | Latency: {m.latency_ms}ms | Hash: {m.context_hash}*")
            lines.append("\n---\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, "\n".join(lines))
        return True
    except Exception as e:
        print(f"[ChatService] Export error: {e}")
        return False


# =============================================================================
# CHAT SERVICE
# =============================================================================

class ChatService:
    """
    Service for communicating with ROXY through the canonical harness.

    Responsibilities:
    - Send messages to roxy-chat-proxy :4001 /v1/chat/completions
    - Manage session state (with disk persistence)
    - Maintain OpenAI-style messages[] history
    - Notify UI of responses (via callbacks)
    - Handle connection status
    - Surface roxy metadata: memoryRefs, proposedActions, latency, model

    Does NOT:
    - Call Ollama /api/generate directly
    - Call LiteLLM :4000 directly
    - Call Qwen :8085 directly
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

        # Phase 6: Service hardening — circuit breaker + exponential backoff
        self._consecutive_failures: int = 0
        self._circuit_open: bool = False
        self._circuit_cooldown_until: Optional[datetime] = None
        self._CIRCUIT_THRESHOLD: int = 5  # Open circuit after 5 consecutive failures
        self._CIRCUIT_COOLDOWN_SECONDS: int = 30  # Stay open for 30s
        self._MAX_BACKOFF_SECONDS: int = 16  # Max health check backoff

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

        # Session persistence
        self._persisted_state = _load_session_state()

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
        Connect to ROXY harness and create/load a session.
        """
        self._on_message = on_message
        self._on_status_change = on_status_change
        self._on_typing = on_typing
        self._on_meta_update = on_meta_update

        # Restore session from disk (roxy_session_id + conversation history)
        restored_session_id = self._persisted_state.get("roxy_session_id")
        restored_messages = self.load_session_messages()

        self._session = ChatSession(
            id=str(uuid.uuid4()),
            identity=identity,
            mode=ChatMode.DRAFT,
            messages=restored_messages,
            created_at=datetime.now(),
            roxy_session_id=restored_session_id,
        )
        
        # Replay restored messages to UI
        if restored_messages and on_message:
            for m in restored_messages:
                on_message(m)

        # Test connection to harness
        self._set_status(ConnectionStatus.CONNECTING, "Connecting to ROXY harness...")
        self._ping_harness()

    def disconnect(self):
        """Disconnect from ROXY harness."""
        self._session = None
        self._set_status(ConnectionStatus.DISCONNECTED, "Disconnected")

    # -------------------------------------------------------------------------
    # Session persistence (Phase 4: Save-authority UX)
    # -------------------------------------------------------------------------

    def save_session(self) -> bool:
        """Persist full conversation history to disk."""
        if not self._session:
            return False
        try:
            state = {
                "roxy_session_id": self._session.roxy_session_id,
                "identity": self._session.identity.value,
                "mode": self._session.mode.value,
                "created_at": self._session.created_at.isoformat(),
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat(),
                        "identity": m.identity.value,
                        "latency_ms": m.latency_ms,
                        "model": m.model,
                        "memory_refs": m.memory_refs,
                        "proposed_actions": m.proposed_actions,
                        "context_hash": m.context_hash,
                        "context_kernel_version": m.context_kernel_version,
                        "source_health": m.source_health,
                        "token_budget": m.token_budget,
                        "orico_counts": m.orico_counts,
                        "degraded_reasons": m.degraded_reasons,
                        "harness_bypassed": m.harness_bypassed,
                    }
                    for m in self._session.messages
                ],
            }
            _save_session_state(state)
            return True
        except Exception as e:
            print(f"[ChatService] save_session error: {e}")
            return False

    def load_session_messages(self) -> List[ChatMessage]:
        """Restore conversation messages from disk."""
        try:
            state = _load_session_state()
            msgs = state.get("messages", [])
            return [
                ChatMessage(
                    id=m.get("id", str(uuid.uuid4())),
                    role=m["role"],
                    content=m["content"],
                    timestamp=datetime.fromisoformat(m["timestamp"]),
                    identity=Identity(m.get("identity", "mindsong")),
                    latency_ms=m.get("latency_ms", 0),
                    model=m.get("model", ""),
                    memory_refs=m.get("memory_refs", []),
                    proposed_actions=m.get("proposed_actions", []),
                    context_hash=m.get("context_hash", ""),
                    context_kernel_version=m.get("context_kernel_version", ""),
                    source_health=m.get("source_health", {}),
                    token_budget=m.get("token_budget", {}),
                    orico_counts=m.get("orico_counts", {}),
                    degraded_reasons=m.get("degraded_reasons", []),
                    harness_bypassed=m.get("harness_bypassed", False),
                )
                for m in msgs
            ]
        except Exception as e:
            print(f"[ChatService] load_session_messages error: {e}")
            return []

    def clear_session(self) -> bool:
        """Clear conversation history and reset session."""
        if not self._session:
            return False
        self._session.messages.clear()
        self._session.roxy_session_id = None
        try:
            _save_session_state({})
            return True
        except Exception as e:
            print(f"[ChatService] clear_session error: {e}")
            return False

    def export_to_markdown(self, path: Optional[Path] = None) -> Optional[Path]:
        """Export conversation to markdown file."""
        if not self._session or not self._session.messages:
            return None
        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = Path.home() / ".config" / "roxy-command-center" / "exports" / f"conversation-{ts}.md"
        if _export_session_to_markdown(self._session.messages, path):
            return path
        return None

    def send_message(self, text: str, routing_mode: str = "", pool: str = "") -> Optional[ChatMessage]:
        """
        Send a message to ROXY and get a response.

        Args:
            text: The user's message
            routing_mode: Explicit routing mode (CHAT/RAG/EXEC) — empty means auto
            pool: Explicit pool, currently ignored unless ROXY/AUTO

        Returns:
            The user message (assistant response comes via callback)
        """
        if not self._session:
            print("[ChatService] No session, cannot send")
            return None

        if not text.strip():
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

        # Send to ROXY harness
        self._send_to_harness(text, routing_mode=routing_mode, pool=pool)

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

    # -------------------------------------------------------------------------
    # Internal: ROXY harness communication
    # -------------------------------------------------------------------------

    def _ping_harness(self, retry_count: int = 0):
        """Test connection to roxy-chat-proxy via /health endpoint."""
        # Phase 6: Circuit breaker check
        if self._circuit_open:
            if self._circuit_cooldown_until and datetime.now() < self._circuit_cooldown_until:
                remaining = int((self._circuit_cooldown_until - datetime.now()).total_seconds())
                self._set_status(ConnectionStatus.ERROR, f"Circuit open — retry in {remaining}s")
                return
            else:
                # Half-open: try one request
                self._circuit_open = False
                self._consecutive_failures = 0
                print("[ChatService] Circuit half-open, attempting recovery...")

        uri = f"{self._proxy_base_url}/health"
        message = Soup.Message.new("GET", uri)

        self._soup_session.send_async(
            message, GLib.PRIORITY_DEFAULT, None,
            self._on_ping_response, retry_count
        )

    def _on_ping_response(self, session, result, retry_count):
        """Handle ping response from /health."""
        retry_count = retry_count if isinstance(retry_count, int) else 0
        try:
            input_stream = session.send_finish(result)
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
                    if status.get("ok"):
                        upstream_ok = status.get("upstreamReachable", False)
                        svc = status.get("service", "roxy-chat-proxy")
                        prompt_loaded = status.get("promptLoaded", False)
                        skill_count = status.get("skillEmbeddingsLoaded", 0)
                        storage = status.get("storage", {})
                        storage_status = storage.get("status", "unknown")

                        status_state = ConnectionStatus.CONNECTED if upstream_ok else ConnectionStatus.ERROR
                        status_message = (
                            f"{svc} ready • upstream={'OK' if upstream_ok else 'DOWN'} "
                            f"• prompt={'loaded' if prompt_loaded else 'missing'} "
                            f"• skills={skill_count} • store={storage_status}"
                        )

                        # Phase 6: Reset circuit breaker on success
                        if self._consecutive_failures > 0:
                            print(f"[ChatService] Circuit reset after {self._consecutive_failures} failures")
                            self._consecutive_failures = 0
                            self._circuit_open = False
                            self._circuit_cooldown_until = None

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
                    else:
                        self._set_status(ConnectionStatus.ERROR, "Harness returned ok=false")
                except json.JSONDecodeError:
                    self._set_status(ConnectionStatus.CONNECTED, "Connected (non-JSON health)")
            else:
                self._set_status(ConnectionStatus.CONNECTED, "Connected (empty health)")

        except Exception as e:
            error_str = str(e)
            is_timeout = "timed out" in error_str.lower() or "timeout" in error_str.lower()

            # Phase 6: Exponential backoff for retries
            if is_timeout and retry_count < 3:
                backoff = min(2 ** retry_count, self._MAX_BACKOFF_SECONDS)
                print(f"[ChatService] Ping timeout, retry {retry_count + 1}/3 in {backoff}s...")
                GLib.timeout_add_seconds(backoff, lambda: self._ping_harness(retry_count + 1) or False)
                return

            # Phase 6: Circuit breaker — count consecutive failures
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._CIRCUIT_THRESHOLD:
                self._circuit_open = True
                self._circuit_cooldown_until = datetime.now() + __import__('datetime').timedelta(seconds=self._CIRCUIT_COOLDOWN_SECONDS)
                print(f"[ChatService] Circuit OPEN after {self._consecutive_failures} failures. Cooldown {self._CIRCUIT_COOLDOWN_SECONDS}s.")

            print(f"[ChatService] Ping failed: {e}")
            self._set_status(ConnectionStatus.ERROR, f"Harness unreachable: {e}")

    def _build_messages(self) -> List[Dict[str, str]]:
        """Build OpenAI-compatible messages[] from session history."""
        if not self._session:
            return []
        msgs = []
        for m in self._session.messages:
            # Only include user and assistant roles in the API payload
            if m.role in ("user", "assistant"):
                msgs.append({"role": m.role, "content": m.content})
        return msgs

    def _send_to_harness(self, text: str, routing_mode: str = "", pool: str = ""):
        """Send message to roxy-chat-proxy :4001 /v1/chat/completions.

        Args:
            text: The message to send
            routing_mode: Recorded as metadata only
            pool: Ignored unless AUTO/ROXY
        """
        uri = f"{self._proxy_base_url}/v1/chat/completions"
        message = Soup.Message.new("POST", uri)

        headers = message.get_request_headers()
        headers.append("Content-Type", "application/json")

        # Build OpenAI-compatible payload
        model = DEFAULT_MODEL
        # If user explicitly set a non-default model via prior meta, respect it
        if self._last_model and self._last_model != "unknown" and self._last_model != "roxy-coder-frontier":
            model = self._last_model

        # Build messages array from conversation history
        messages = self._build_messages()
        # If the last message isn't already in history (it should be), ensure it is
        if not messages or messages[-1].get("content") != text:
            messages.append({"role": "user", "content": text})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2048,
            "chat_template_kwargs": {
                "enable_thinking": False,
            },
        }

        # Include session_id for persistence if we have one
        if self._session and self._session.roxy_session_id:
            payload["session_id"] = self._session.roxy_session_id

        # Add explicit operator controls (Chief's Truth Panel)
        if routing_mode and routing_mode != "AUTO":
            payload["roxy_route_mode"] = routing_mode

        body_bytes = json.dumps(payload).encode('utf-8')
        message.set_request_body_from_bytes("application/json", GLib.Bytes.new(body_bytes))

        start_time = GLib.get_monotonic_time()
        self._request_start_time = start_time
        self._pending_request_active = True
        self._timeout_error_triggered = False
        self._last_error_message = None
        self._cancel_status_timeouts()
        self._set_status(ConnectionStatus.CONNECTING, "Sending to ROXY harness...")
        self._pending_message = message

        print(f"[ChatService] Sending to {uri} model={model} msgs={len(messages)}")

        self._soup_session.send_async(
            message,
            GLib.PRIORITY_DEFAULT,
            None,
            self._on_chat_response,
            None
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
            message = f"Timed out waiting for first token. Check harness at {host}/health"
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

    def _on_chat_response(self, session, result, user_data):
        """Handle /v1/chat/completions response from roxy-chat-proxy."""
        print("[ChatService] Response callback triggered")
        self._cancel_status_timeouts()
        self._pending_request_active = False
        self._pending_message = None
        self._timeout_error_triggered = False

        # Hide typing indicator
        if self._on_typing:
            self._on_typing(False)

        try:
            input_stream = session.send_finish(result)

            # Calculate latency
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
            except json.JSONDecodeError as e:
                # Maybe it's plain text?
                if response_text.strip():
                    self._emit_assistant_message(response_text, "raw")
                    self._set_status(
                        ConnectionStatus.CONNECTED,
                        f"Response received in {self._last_latency_ms}ms"
                    )
                else:
                    self._handle_error(f"Invalid response: {e}")
                return

            # Check for proxy-level errors
            if "error" in data and not data.get("choices"):
                err_msg = data["error"]
                if isinstance(err_msg, dict):
                    err_msg = err_msg.get("message", str(err_msg))
                self._handle_error(f"Harness error: {err_msg}")
                return

            # Extract assistant content (OpenAI format)
            assistant_text = ""
            choices = data.get("choices", [])
            if choices and isinstance(choices, list):
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    message_obj = first_choice.get("message", {})
                    if isinstance(message_obj, dict):
                        assistant_text = message_obj.get("content", "")

            # Extract model name
            self._last_model = data.get("model", DEFAULT_MODEL)
            self._last_expert = "roxy-harness"

            # Extract roxy metadata
            roxy_meta = data.get("roxy", {}) if isinstance(data.get("roxy"), dict) else {}
            session_id = roxy_meta.get("sessionId") or data.get("session_id")
            memory_refs = roxy_meta.get("memoryRefs", []) or []
            proposed_actions = roxy_meta.get("proposedActions", []) or []
            persistence_status = roxy_meta.get("persistenceStatus", "")
            memory_status = roxy_meta.get("memoryStatus", "")
            context_hash = roxy_meta.get("contextHash", "")
            context_kernel_version = roxy_meta.get("contextKernelVersion", "")
            context_kernel = roxy_meta.get("contextKernel", {}) or {}
            source_health = context_kernel.get("sourceHealth", {}) or {}
            token_budget = context_kernel.get("tokenBudget", {}) or {}
            memory_block = context_kernel.get("memory", {}) or {}
            orico_counts = memory_block.get("orico", {}).get("counts", {}) or {}
            degraded_reasons = context_kernel.get("degradedReasons", []) or []

            # Persist session id
            if session_id and self._session:
                self._session.roxy_session_id = session_id
                self._persisted_state["roxy_session_id"] = session_id
                _save_session_state(self._persisted_state)

            # Build execution metadata for Truth Panel
            meta = {
                "mode": "ROXY",
                "pool": "AUTO",
                "route": "harness",
                "model_used": self._last_model,
                "total_ms": self._last_latency_ms,
                "session_id": session_id,
                "persistence_status": persistence_status,
                "memory_status": memory_status,
                "memory_refs_count": len(memory_refs),
                "proposed_actions_count": len(proposed_actions),
                "context_hash": context_hash,
                "context_kernel_version": context_kernel_version,
                "source_health": source_health,
                "token_budget": token_budget,
                "orico_counts": orico_counts,
                "degraded_reasons": degraded_reasons,
            }
            self._last_execution_meta = meta
            if self._on_meta_update:
                self._on_meta_update(meta)

            print(f"[ChatService] Roxy meta: session={session_id} refs={len(memory_refs)} actions={len(proposed_actions)}")

            # Harness bypass detection
            # ROXY-harnessed responses MUST contain ROXY identity markers.
            # Generic base-model responses ("Alibaba Cloud", "Qwen", "AI language model")
            # without ROXY context = harness bypassed.
            generic_markers = [
                "Alibaba Cloud",
                "developed by Alibaba",
                "I am Qwen",
                "I am a large language model",
                "I am an AI language model",
                "I don't have information about ROXY",
                "I don't have information about MindSong",
            ]
            roxy_markers = [
                "ROXY",
                "Roxy Command Center",
                "MindSong",
                "Mark",
                "local brain",
                "memory",
                "harness",
                "estate",
            ]
            has_generic = any(m.lower() in assistant_text.lower() for m in generic_markers)
            has_roxy = any(m.lower() in assistant_text.lower() for m in roxy_markers)
            
            harness_bypassed = has_generic and not has_roxy
            if harness_bypassed:
                # Harness bypassed — prepend warning
                warning = (
                    "🚨 HARNESS BYPASSED 🚨\n"
                    "The response came from the raw base model, not the ROXY harness.\n"
                    "Expected: ROXY identity + Mark context + MindSong estate.\n"
                    "Got: Generic provider response.\n"
                    "---\n\n"
                )
                assistant_text = warning + assistant_text
                self._set_status(
                    ConnectionStatus.ERROR,
                    "HARNESS BYPASSED — raw base model response"
                )
                # Override model to signal bypass
                self._last_model = "HARNESS-BYPASSED"
                if self._on_meta_update:
                    self._last_execution_meta["harness_bypassed"] = True
                    self._last_execution_meta["model_used"] = "HARNESS-BYPASSED"
                    self._on_meta_update(self._last_execution_meta)

            if assistant_text:
                self._emit_assistant_message(
                    assistant_text,
                    model=self._last_model,
                    latency_ms=self._last_latency_ms,
                    memory_refs=memory_refs,
                    proposed_actions=proposed_actions,
                    context_hash=context_hash,
                    context_kernel_version=context_kernel_version,
                    source_health=source_health,
                    token_budget=token_budget,
                    orico_counts=orico_counts,
                    degraded_reasons=degraded_reasons,
                    harness_bypassed=harness_bypassed,
                )
                if not has_generic:
                    self._set_status(
                        ConnectionStatus.CONNECTED,
                        f"Response received in {self._last_latency_ms}ms"
                    )
                self._last_error_message = None
            else:
                self._handle_error("Empty response from ROXY harness")

        except Exception as e:
            print(f"[ChatService] Error: {e}")
            self._handle_error(str(e))

    def _emit_assistant_message(
        self,
        content: str,
        model: str = "",
        latency_ms: int = 0,
        memory_refs: Optional[List[str]] = None,
        proposed_actions: Optional[List[str]] = None,
        context_hash: str = "",
        context_kernel_version: str = "",
        source_health: Optional[Dict[str, Any]] = None,
        token_budget: Optional[Dict[str, Any]] = None,
        orico_counts: Optional[Dict[str, Any]] = None,
        degraded_reasons: Optional[List[str]] = None,
        harness_bypassed: bool = False,
    ):
        """Emit an assistant message with full harness metadata."""
        assistant_msg = ChatMessage(
            id=str(uuid.uuid4()),
            role="assistant",
            content=content,
            timestamp=datetime.now(),
            identity=self._session.identity if self._session else Identity.MINDSONG,
            latency_ms=latency_ms,
            model=model,
            memory_refs=memory_refs or [],
            proposed_actions=proposed_actions or [],
            context_hash=context_hash,
            context_kernel_version=context_kernel_version,
            source_health=source_health or {},
            token_budget=token_budget or {},
            orico_counts=orico_counts or {},
            degraded_reasons=degraded_reasons or [],
            harness_bypassed=harness_bypassed,
        )

        if self._session:
            self._session.messages.append(assistant_msg)

        if self._on_message:
            self._on_message(assistant_msg)
        
        # Phase 4: Auto-save after every assistant response
        self.save_session()

    def _handle_error(self, error: str):
        """Handle error response."""
        self._cancel_status_timeouts()
        self._pending_request_active = False
        self._pending_message = None
        if self._on_typing:
            self._on_typing(False)
        self._set_status(ConnectionStatus.ERROR, error)
        if error == self._last_error_message:
            return
        self._last_error_message = error
        
        # Phase 6: Auto-reconnect on connection errors
        error_lower = error.lower()
        is_connection_error = any(k in error_lower for k in [
            "unreachable", "connection", "refused", "reset", "timeout",
            "cannot connect", "failed to connect", "no route"
        ])
        if is_connection_error:
            print(f"[ChatService] Connection error detected, triggering health check...")
            GLib.timeout_add_seconds(2, lambda: self._ping_harness() or False)
        
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
        self._is_recording = True
        print("[VoiceService] Recording started (stub)")
        if self._on_recording_change:
            self._on_recording_change(True)

    def stop_recording(self):
        """Stop recording and transcribe."""
        self._is_recording = False
        print("[VoiceService] Recording stopped (stub)")
        if self._on_recording_change:
            self._on_recording_change(False)

    def speak(self, text: str):
        """Request TTS for text (Option B: manual speak button)."""
        if not self._speak_mode:
            print("[VoiceService] Speak mode disabled")
            return
        print(f"[VoiceService] Speak request (stub): {text[:50]}...")

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
