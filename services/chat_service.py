#!/usr/bin/env python3
"""
Chat Service - current ROXY adapter.

DOCTRINE:
- GTK app stays thin client
- Current review build talks directly to the local Ollama service
- No production core service is assumed

Endpoints used:
- GET /api/tags - health/model list
- POST /api/generate - foreground chat smoke
"""

import gi
gi.require_version('Soup', '3.0')
from gi.repository import GLib, Soup, Gio
import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable, List
from datetime import datetime
from enum import Enum
import uuid


# =============================================================================
# CONFIGURATION
# =============================================================================

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("ROXY_COMMAND_CENTER_MODEL", "tinyllama")


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
    """Connection state to local Ollama."""
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


@dataclass
class ChatSession:
    """A chat session with current ROXY."""
    id: str
    identity: Identity
    mode: ChatMode
    messages: List[ChatMessage]
    created_at: datetime
    model: str = "unknown"
    

# =============================================================================
# CHAT SERVICE
# =============================================================================

class ChatService:
    """
    Service for communicating with current ROXY.
    
    Responsibilities:
    - Send review-only messages to local Ollama
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
        self._ollama_base_url: str = OLLAMA_BASE_URL
        
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
        Connect to local Ollama and create/load a session.
        
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
        
        # Test connection
        self._set_status(ConnectionStatus.CONNECTING, "Connecting to local Ollama...")
        self._ping_roxy_core()
    
    def disconnect(self):
        """Disconnect from local Ollama."""
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
        
        # Send to local Ollama with operator controls
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
    
    # -------------------------------------------------------------------------
    # Internal: local Ollama communication
    # -------------------------------------------------------------------------
    
    def _ping_roxy_core(self, retry_count: int = 0):
        """Test connection to Ollama via /api/tags endpoint.
        
        Args:
            retry_count: Current retry attempt (max 2 retries on timeout)
        """
        uri = f"{self._ollama_base_url}/api/tags"
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
                    models = status.get("models", [])
                    status_state = ConnectionStatus.CONNECTED
                    model_names = [m.get("name", "") for m in models if isinstance(m, dict)]
                    self._last_model = DEFAULT_MODEL if DEFAULT_MODEL in model_names else (model_names[0] if model_names else DEFAULT_MODEL)
                    status_message = f"Ollama ready at {self._ollama_base_url} ({len(model_names)} models)"

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
                except json.JSONDecodeError:
                    self._set_status(ConnectionStatus.CONNECTED, "Connected")
            else:
                self._set_status(ConnectionStatus.CONNECTED, "Connected (no status)")
                
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
        """Send message to local Ollama /api/generate endpoint.

        Args:
            text: The message to send
            routing_mode: Recorded as metadata only in this direct adapter
            pool: Ignored unless AUTO/ROXY in this direct adapter
        """
        uri = f"{self._ollama_base_url}/api/generate"
        message = Soup.Message.new("POST", uri)
        
        # Set headers
        headers = message.get_request_headers()
        headers.append("Content-Type", "application/json")
        # Build payload
        model = self._last_model if self._last_model and self._last_model != "unknown" else DEFAULT_MODEL
        payload = {
            "model": model,
            "prompt": text,
            "stream": False,
            "options": {
                "temperature": 0.2
            }
        }
        
        # Add explicit operator controls (Chief's Truth Panel)
        if routing_mode and routing_mode != "AUTO":
            payload["roxy_route_mode"] = routing_mode
        
        # Set body
        body_bytes = json.dumps(payload).encode('utf-8')
        message.set_request_body_from_bytes("application/json", GLib.Bytes.new(body_bytes))
        
        # Record start time for latency
        start_time = GLib.get_monotonic_time()
        
        # Store start_time as instance var since user_data doesn't work reliably
        self._request_start_time = start_time
        self._pending_request_active = True
        self._timeout_error_triggered = False
        self._last_error_message = None
        self._cancel_status_timeouts()
        self._set_status(ConnectionStatus.CONNECTING, "Sending…")
        self._pending_message = message
        
        print(f"[ChatService] Sending to {uri}...")
        
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
            host = self._ollama_base_url or OLLAMA_BASE_URL
            message = f"Timed out waiting for first token. Check Ollama host at {host}"
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
        """Handle /api/generate response from local Ollama."""
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
            
            if response_text:
                try:
                    data = json.loads(response_text)
                    
                    # Extract response
                    assistant_text = data.get("response", data.get("result", ""))
                    self._last_expert = "local-ollama"
                    if data.get("model"):
                        self._last_model = data["model"]
                    
                    # Updates for Chief's Truth Panel metadata
                    if "metadata" in data:
                        meta = data["metadata"]
                        self._last_execution_meta = meta
                        
                        # Notify UI if callback registered
                        if self._on_meta_update:
                            self._on_meta_update(meta)
                        
                        print(f"[ChatService] Execution metadata: {json.dumps(meta)}")
                    
                    if assistant_text:
                        # Create assistant message
                        assistant_msg = ChatMessage(
                            id=str(uuid.uuid4()),
                            role="assistant",
                            content=assistant_text,
                            timestamp=datetime.now(),
                            identity=self._session.identity if self._session else Identity.MINDSONG
                        )
                        
                        if self._session:
                            self._session.messages.append(assistant_msg)
                        
                        if self._on_message:
                            self._on_message(assistant_msg)
                        self._set_status(
                            ConnectionStatus.CONNECTED,
                            f"Response received in {self._last_latency_ms}ms"
                        )
                        self._last_error_message = None
                    else:
                        self._handle_error("Empty response from Roxy")
                        
                except json.JSONDecodeError as e:
                    # Maybe it's plain text?
                    if response_text.strip():
                        assistant_msg = ChatMessage(
                            id=str(uuid.uuid4()),
                            role="assistant",
                            content=response_text,
                            timestamp=datetime.now()
                        )
                        if self._session:
                            self._session.messages.append(assistant_msg)
                        if self._on_message:
                            self._on_message(assistant_msg)
                        self._set_status(
                            ConnectionStatus.CONNECTED,
                            f"Response received in {self._last_latency_ms}ms"
                        )
                        self._last_error_message = None
                    else:
                        self._handle_error(f"Invalid response: {e}")
            else:
                    self._handle_error("No response from local Ollama")
                
        except Exception as e:
            print(f"[ChatService] Error: {e}")
            self._handle_error(str(e))
    
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
