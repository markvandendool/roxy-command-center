#!/usr/bin/env python3
"""
Ollama API control service.
Provides model unload, list, and health check operations.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib
import threading
import json
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class ActionResult(Enum):
    """Operation result."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"


@dataclass
class OllamaAction:
    """Result of an Ollama operation."""
    pool: str
    action: str
    model: str
    result: ActionResult
    message: str = ""


# Current ROXY has one production Ollama service.
# Keep aliases harmlessly pointed at the same endpoint so old UI settings do not
# create phantom controls or a second port.
POOL_CONFIG = {
    "ROXY": {"url": "http://127.0.0.1:11434", "port": 11434},
    "AUTO": {"url": "http://127.0.0.1:11434", "port": 11434},
    "ollama": {"url": "http://127.0.0.1:11434", "port": 11434},
    "local": {"url": "http://127.0.0.1:11434", "port": 11434},
}


class OllamaControl:
    """
    Ollama API control for model management.

    Operations:
    - unload_model: Unload a model from GPU memory
    - list_models: Get loaded models for a pool
    - check_health: Check if Ollama endpoint is responsive
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def get_pool_url(self, pool: str) -> Optional[str]:
        """Get Ollama URL for pool name."""
        config = POOL_CONFIG.get(pool) or POOL_CONFIG.get(pool.upper())
        return config["url"] if config else None

    def unload_model(self, pool: str, model: str,
                     callback: Optional[Callable[[OllamaAction], None]] = None):
        """
        Unload a model from GPU memory.

        Uses POST /api/generate with keep_alive: "0" to trigger immediate unload.
        Runs in background thread, callback invoked on main thread.
        """
        if not REQUESTS_AVAILABLE:
            if callback:
                result = OllamaAction(
                    pool=pool, action="unload", model=model,
                    result=ActionResult.FAILED,
                    message="requests library not installed"
                )
                GLib.idle_add(lambda: callback(result))
            return

        def worker():
            result = self._unload_model_sync(pool, model)
            if callback:
                GLib.idle_add(lambda: callback(result))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _unload_model_sync(self, pool: str, model: str) -> OllamaAction:
        """Synchronous model unload (runs in worker thread)."""
        url = self.get_pool_url(pool)
        if not url:
            return OllamaAction(
                pool=pool, action="unload", model=model,
                result=ActionResult.NOT_FOUND,
                message=f"Unknown pool: {pool}"
            )

        try:
            # Method 1: POST /api/generate with keep_alive: 0
            # This generates nothing and then immediately unloads
            response = requests.post(
                f"{url}/api/generate",
                json={
                    "model": model,
                    "prompt": "",
                    "keep_alive": 0  # Unload immediately after this request
                },
                timeout=self.timeout
            )

            if response.status_code == 200:
                return OllamaAction(
                    pool=pool, action="unload", model=model,
                    result=ActionResult.SUCCESS,
                    message=f"Model {model} unloaded from {pool}"
                )
            elif response.status_code == 404:
                return OllamaAction(
                    pool=pool, action="unload", model=model,
                    result=ActionResult.NOT_FOUND,
                    message=f"Model {model} not found on {pool}"
                )
            else:
                return OllamaAction(
                    pool=pool, action="unload", model=model,
                    result=ActionResult.FAILED,
                    message=f"HTTP {response.status_code}: {response.text[:100]}"
                )

        except requests.Timeout:
            return OllamaAction(
                pool=pool, action="unload", model=model,
                result=ActionResult.TIMEOUT,
                message=f"Request timeout ({self.timeout}s)"
            )
        except requests.RequestException as e:
            return OllamaAction(
                pool=pool, action="unload", model=model,
                result=ActionResult.FAILED,
                message=str(e)
            )

    def list_loaded_models(self, pool: str) -> List[Dict[str, Any]]:
        """Get list of loaded models for a pool (synchronous)."""
        if not REQUESTS_AVAILABLE:
            return []

        url = self.get_pool_url(pool)
        if not url:
            return []

        try:
            response = requests.get(f"{url}/api/ps", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                result = []
                for m in models:
                    result.append({
                        "name": m.get("name", "unknown"),
                        "size": m.get("size", 0),
                        "vram_gb": m.get("size_vram", 0) / (1024**3) if m.get("size_vram") else 0,
                        "expires_at": m.get("expires_at", ""),
                    })
                return result
        except Exception:
            pass
        return []

    def check_health(self, pool: str) -> bool:
        """Check if Ollama endpoint is healthy."""
        if not REQUESTS_AVAILABLE:
            return False

        url = self.get_pool_url(pool)
        if not url:
            return False

        try:
            response = requests.get(f"{url}/api/tags", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False


# Global instance
_ollama_control: Optional[OllamaControl] = None


def get_ollama_control() -> OllamaControl:
    """Get or create global Ollama control instance."""
    global _ollama_control
    if _ollama_control is None:
        _ollama_control = OllamaControl()
    return _ollama_control
