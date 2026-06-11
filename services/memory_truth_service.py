#!/usr/bin/env python3
"""
MemoryTruthService — Single GTK service for ROXY memory truth.

Surfaces:
- Qdrant points / indexed vector count / retrieval mode
- SQLite brain store health and counts
- Context fallback mode (bridge vs direct)
- Latest session + transcript
- RAG quality status
- Memory candidates (pending/provisional facts)

Sources:
- roxy-chat-proxy :4001 /health
- roxy-chat-proxy :4001 /sessions/latest
- roxy-chat-proxy :4001 /memory-candidates
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

import gi
gi.require_version("Soup", "3.0")
from gi.repository import GLib, Soup


ROXY_CHAT_PROXY_URL = "http://127.0.0.1:4001"
MEMORY_TTL_SECONDS = 5.0


@dataclass
class MemoryTruthSnapshot:
    """Normalized memory truth snapshot."""
    ok: bool = False
    timestamp: str = ""
    generated_at: datetime = field(default_factory=datetime.now)
    qdrant: Dict[str, Any] = field(default_factory=dict)
    brain_storage: Dict[str, Any] = field(default_factory=dict)
    memory_status: Dict[str, Any] = field(default_factory=dict)
    rag_status: Dict[str, Any] = field(default_factory=dict)
    latest_session: Dict[str, Any] = field(default_factory=dict)
    latest_transcript: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    fallback_used: bool = False
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "timestamp": self.timestamp,
            "generatedAt": self.generated_at.isoformat(),
            "qdrant": self.qdrant,
            "brainStorage": self.brain_storage,
            "memoryStatus": self.memory_status,
            "ragStatus": self.rag_status,
            "latestSession": self.latest_session,
            "latestTranscript": self.latest_transcript,
            "candidates": self.candidates,
            "fallbackUsed": self.fallback_used,
            "error": self.error,
        }


class _Cache:
    def __init__(self):
        self._value: Optional[MemoryTruthSnapshot] = None
        self._at: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> Optional[MemoryTruthSnapshot]:
        with self._lock:
            return self._value

    def set(self, value: MemoryTruthSnapshot):
        with self._lock:
            self._value = value
            self._at = time.time()

    def age(self) -> float:
        with self._lock:
            return time.time() - self._at


class MemoryTruthService:
    """GTK-thread-safe service that reads memory truth from roxy-chat-proxy."""

    def __init__(self, base_url: str = ROXY_CHAT_PROXY_URL):
        self._base_url = base_url.rstrip("/")
        self._session = Soup.Session()
        try:
            self._session.set_property("timeout", 15)
        except Exception:
            pass
        self._cache = _Cache()
        self._last_good: Optional[MemoryTruthSnapshot] = None

    def snapshot(self, *, force: bool = False) -> MemoryTruthSnapshot:
        """Return cached memory truth or refresh from proxy."""
        cached = self._cache.get()
        if not force and cached and self._cache.age() < MEMORY_TTL_SECONDS:
            return cached

        fresh = self._fetch()
        self._cache.set(fresh)
        if fresh.ok:
            self._last_good = fresh
        elif self._last_good:
            stale = self._last_good
            stale.error = fresh.error or "stale"
            return stale
        return fresh

    def _fetch(self) -> MemoryTruthSnapshot:
        health = self._get_json("/health")
        latest = self._get_json("/sessions/latest")
        candidates = self._get_json("/memory-candidates?status=all&limit=20")

        if not health.get("ok") and "error" in health:
            return MemoryTruthSnapshot(ok=False, error=health.get("error", "proxy health failed"))

        memory_status = health.get("memoryStatus") or {}
        storage = health.get("storage") or {}
        qdrant = health.get("qdrant") or {}

        return MemoryTruthSnapshot(
            ok=bool(health.get("ok")),
            timestamp=health.get("timestamp") or datetime.now().isoformat(),
            generated_at=datetime.now(),
            qdrant=qdrant,
            brain_storage=storage,
            memory_status=memory_status,
            rag_status=health.get("ragStatus") or {},
            latest_session=latest.get("latest") or {},
            latest_transcript=latest.get("transcript") or [],
            candidates=candidates.get("candidates") or [],
            fallback_used=bool(memory_status.get("fallbackUsed") or health.get("contextFallbackUsed")),
        )

    def _get_json(self, path: str) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            message = Soup.Message.new("GET", url)
            status, body = self._session.send_and_read_finish(
                self._session.send_and_read(message, None)
            )
            if status:
                data = json.loads(body.get_data().decode("utf-8"))
                return data if isinstance(data, dict) else {"ok": False, "error": "non-object response"}
            return {"ok": False, "error": f"HTTP {message.get_status()}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


_singleton: Optional[MemoryTruthService] = None
_singleton_lock = threading.Lock()


def get_memory_truth_service() -> MemoryTruthService:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = MemoryTruthService()
        return _singleton
