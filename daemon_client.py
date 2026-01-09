#!/usr/bin/env python3
"""
Async daemon client with timeout handling.
ROXY-CMD-STORY-001: Non-blocking HTTP fetches with GLib integration.
"""

import subprocess
import json
import os
import threading
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib

DAEMON_PATH = Path.home() / ".config/eww/roxy-panel/scripts/roxy-panel-daemon.py"
DEFAULT_TIMEOUT = 2.0  # 2 second timeout per ORACLE-04 mitigation
MAX_CACHE_AGE = 30.0   # Cache TTL in seconds

@dataclass
class DaemonResponse:
    """Container for daemon response with metadata."""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    source: str = "unknown"
    error: Optional[str] = None
    is_stale: bool = False

class DaemonClient:
    """
    Async daemon client with caching and GLib integration.
    
    Features:
    - Thread pool for non-blocking HTTP fetches
    - 2s timeout to prevent UI freeze (ORACLE-04)
    - Response caching with staleness indicator
    - GLib.idle_add for safe UI updates
    """
    
    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="daemon")
        self._cache: Optional[DaemonResponse] = None
        self._pending = False
        self._callbacks: list = []
        
        # Mode configuration
        self.mode = "auto"
        self.remote_host = "10.0.0.69"
        self.remote_port = 8766
    
    def configure(self, mode: str = "auto", remote_host: str = "10.0.0.69", remote_port: int = 8766):
        """Update daemon connection configuration."""
        self.mode = mode
        self.remote_host = remote_host
        self.remote_port = remote_port
    
    def get_cached(self) -> Optional[DaemonResponse]:
        """Get cached response if available and fresh."""
        if self._cache is None:
            return None
        
        age = time.time() - self._cache.timestamp
        if age > MAX_CACHE_AGE:
            self._cache.is_stale = True
        
        return self._cache
    
    def fetch_async(self, callback: Callable[[DaemonResponse], None]):
        """
        Fetch daemon status asynchronously.
        
        Callback will be invoked on main thread via GLib.idle_add.
        If a fetch is already pending, callback is queued.
        """
        self._callbacks.append(callback)
        
        if self._pending:
            return  # Already fetching, callback will be called when complete
        
        self._pending = True
        self.executor.submit(self._fetch_worker)
    
    def _fetch_worker(self):
        """Worker thread: fetch from daemon and schedule callback."""
        response = self._do_fetch()
        
        # Cache the response
        self._cache = response
        
        # Schedule UI update on main thread
        GLib.idle_add(self._deliver_callbacks, response)
    
    def _deliver_callbacks(self, response: DaemonResponse) -> bool:
        """Deliver response to all waiting callbacks (main thread)."""
        self._pending = False
        callbacks = self._callbacks[:]
        self._callbacks.clear()
        
        for cb in callbacks:
            try:
                cb(response)
            except Exception as e:
                print(f"[DaemonClient] Callback error: {e}")
        
        return False  # Don't repeat
    
    def _do_fetch(self) -> DaemonResponse:
        """Synchronous fetch (runs in worker thread)."""
        env = os.environ.copy()
        env.update({
            "ROXY_MODE": self.mode,
            "ROXY_REMOTE_HOST": self.remote_host,
            "ROXY_REMOTE_PORT": str(self.remote_port),
        })
        
        try:
            result = subprocess.run(
                ["python3", str(DAEMON_PATH), "--mode", "oneshot"],
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return DaemonResponse(
                    error=f"Daemon exit code {result.returncode}: {result.stderr}",
                    timestamp=time.time(),
                    source="error"
                )
            
            data = json.loads(result.stdout)
            return DaemonResponse(
                data=data,
                timestamp=time.time(),
                source=data.get("source", "unknown")
            )
        
        except subprocess.TimeoutExpired:
            return DaemonResponse(
                error=f"Daemon timeout ({self.timeout}s)",
                timestamp=time.time(),
                source="timeout"
            )
        except json.JSONDecodeError as e:
            return DaemonResponse(
                error=f"JSON parse error: {e}",
                timestamp=time.time(),
                source="parse_error"
            )
        except Exception as e:
            return DaemonResponse(
                error=f"Daemon call failed: {e}",
                timestamp=time.time(),
                source="error"
            )
    
    def fetch_sync(self) -> DaemonResponse:
        """
        Synchronous fetch (blocking).
        Use sparingly - prefer fetch_async for UI code.
        """
        return self._do_fetch()
    
    def shutdown(self):
        """Clean shutdown of thread pool."""
        self.executor.shutdown(wait=False)


# Global client instance
_client: Optional[DaemonClient] = None

def get_client() -> DaemonClient:
    """Get or create global daemon client."""
    global _client
    if _client is None:
        _client = DaemonClient()
    return _client

def get_status(mode="auto", remote_host="10.0.0.69", remote_port=8766) -> dict:
    """
    Legacy sync interface for backward compatibility.
    Returns dict with status data or error.
    """
    client = get_client()
    client.configure(mode, remote_host, remote_port)
    response = client.fetch_sync()
    
    if response.error:
        return {"error": response.error}
    return response.data

def fetch_status_async(callback: Callable[[DaemonResponse], None], 
                       mode="auto", remote_host="10.0.0.69", remote_port=8766):
    """
    Async fetch interface.
    Callback receives DaemonResponse on main thread.
    """
    client = get_client()
    client.configure(mode, remote_host, remote_port)
    client.fetch_async(callback)
