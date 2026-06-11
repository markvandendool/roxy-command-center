#!/usr/bin/env python3
"""
Factory Truth Service v2 — GTK cache over the SSOT RCC DARK FACTORY commands.

Provides:
  - TTL-backed caching for factory.status and factory.routes
  - Stale detection with last-good snapshot fallback
  - Per-service / per-route lookups
  - Provenance: source command, timestamp, receiptPath, duration

This module contains no command logic. It delegates to RCCAdapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Dict, Optional

from services.rcc_adapter import RCCAdapter, RCCRunResult


UNKNOWN_VERDICT = "UNKNOWN"
STATUS_TTL_SECONDS = 5.0
ROUTES_TTL_SECONDS = 15.0


@dataclass
class FactoryTruthSnapshot:
    """Normalized snapshot of a factory command result."""

    command_id: str = ""
    verdict: str = UNKNOWN_VERDICT
    ok: bool = False
    ready: Dict[str, bool] = field(default_factory=dict)
    services_by_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    routes_by_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    receipt_path: Optional[str] = None
    generated_at: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0
    fetched_at: float = 0.0
    stale: bool = False
    stale_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "commandId": self.command_id,
            "verdict": self.verdict,
            "ok": self.ok,
            "ready": self.ready,
            "servicesById": self.services_by_id,
            "routesById": self.routes_by_id,
            "receiptPath": self.receipt_path,
            "generatedAt": self.generated_at,
            "warnings": self.warnings,
            "errors": self.errors,
            "durationMs": self.duration_ms,
            "fetchedAt": self.fetched_at,
            "stale": self.stale,
            "staleReason": self.stale_reason,
        }

    def provenance(self) -> Dict[str, Any]:
        """Fields required by the green-state gate."""
        return {
            "source": "rcc",
            "command": self.command_id,
            "timestamp": self.generated_at,
            "fetchedAt": self.fetched_at,
            "receiptPath": self.receipt_path,
            "durationMs": self.duration_ms,
            "stale": self.stale,
        }

    @property
    def is_usable(self) -> bool:
        """True if snapshot is fresh or has a last-good fallback."""
        return bool(self.services_by_id or self.routes_by_id or self.ready)


class FactoryTruthService:
    """TTL cache for factory.status and factory.routes with stale fallback."""

    def __init__(self, adapter: Optional[RCCAdapter] = None):
        self.adapter = adapter or RCCAdapter()

        # Command key -> cached snapshot
        self._cache: Dict[str, FactoryTruthSnapshot] = {}
        # Command key -> last successful snapshot (never overwritten on failure)
        self._last_good: Dict[str, FactoryTruthSnapshot] = {}
        # Command key -> monotonic timestamp of last fetch attempt
        self._last_fetch_at: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_status(self, *, force: bool = False) -> FactoryTruthSnapshot:
        """Return factory.status snapshot (cached or fresh)."""
        return self._fetch("factory.status", STATUS_TTL_SECONDS, force,
                           self._from_status_result)

    def get_routes(self, *, force: bool = False) -> FactoryTruthSnapshot:
        """Return factory.routes snapshot (cached or fresh)."""
        return self._fetch("factory.routes", ROUTES_TTL_SECONDS, force,
                           self._from_routes_result)

    def get_service(self, service_id: str, *, force: bool = False) -> Optional[Dict[str, Any]]:
        """Return a single service from factory.status."""
        snap = self.get_status(force=force)
        info = snap.services_by_id.get(service_id)
        if info is None:
            return None
        return {
            **info,
            "_provenance": snap.provenance(),
            "_stale": snap.stale,
        }

    def get_route(self, route_id: str, *, force: bool = False) -> Optional[Dict[str, Any]]:
        """Return a single route from factory.routes."""
        snap = self.get_routes(force=force)
        info = snap.routes_by_id.get(route_id)
        if info is None:
            return None
        return {
            **info,
            "_provenance": snap.provenance(),
            "_stale": snap.stale,
        }

    def is_stale(self, command_id: str = "factory.status") -> bool:
        """True if the latest snapshot for command_id is stale."""
        snap = self._cache.get(command_id)
        return snap.stale if snap else True

    def last_good(self, command_id: str = "factory.status") -> Optional[FactoryTruthSnapshot]:
        """Return the last successful snapshot, even if current is stale."""
        return self._last_good.get(command_id)

    def snapshot(self, *, force: bool = False) -> Dict[str, Any]:
        """Legacy alias: returns factory.status as dict."""
        return self.get_status(force=force).as_dict()

    def route_doctor(self, *, force: bool = False) -> Dict[str, Any]:
        """Legacy alias: returns factory.routes as dict."""
        return self.get_routes(force=force).as_dict()

    # ------------------------------------------------------------------
    # Fetch core
    # ------------------------------------------------------------------

    def _fetch(self, command_id: str, ttl_seconds: float, force: bool,
               parser) -> FactoryTruthSnapshot:
        now = monotonic()
        last_fetch = self._last_fetch_at.get(command_id, 0.0)
        cached = self._cache.get(command_id)

        if not force and cached is not None and (now - last_fetch) < ttl_seconds:
            return cached

        self._last_fetch_at[command_id] = now

        try:
            result = self.adapter.run(command_id, receipt=True)
            snapshot = parser(command_id, result, now)
            snapshot.fetched_at = now
            snapshot.stale = False
            snapshot.stale_reason = None

            # Keep last-good on success only if result is meaningful
            if snapshot.ok or snapshot.is_usable:
                self._last_good[command_id] = snapshot

            self._cache[command_id] = snapshot
            return snapshot

        except Exception as exc:
            # Return last good snapshot, marked stale
            last = self._last_good.get(command_id)
            if last is not None:
                stale_copy = FactoryTruthSnapshot(
                    command_id=last.command_id,
                    verdict=last.verdict,
                    ok=False,
                    ready=last.ready,
                    services_by_id=last.services_by_id,
                    routes_by_id=last.routes_by_id,
                    receipt_path=last.receipt_path,
                    generated_at=last.generated_at,
                    warnings=last.warnings,
                    errors=last.errors + [f"Refresh failed: {exc}"],
                    duration_ms=last.duration_ms,
                    fetched_at=now,
                    stale=True,
                    stale_reason=str(exc),
                )
                self._cache[command_id] = stale_copy
                return stale_copy

            # No last good: return empty failed snapshot
            failed = FactoryTruthSnapshot(
                command_id=command_id,
                verdict="FAIL",
                ok=False,
                errors=[str(exc)],
                fetched_at=now,
                stale=True,
                stale_reason=str(exc),
            )
            self._cache[command_id] = failed
            return failed

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _from_status_result(command_id: str, result: RCCRunResult, now: float) -> FactoryTruthSnapshot:
        data = result.data if isinstance(result.data, dict) else {}
        services = {}
        for service in data.get("services", []) or []:
            if isinstance(service, dict) and service.get("id"):
                services[service["id"]] = service
        return FactoryTruthSnapshot(
            command_id=command_id,
            verdict=result.verdict,
            ok=result.ok,
            ready=data.get("ready", {}) if isinstance(data.get("ready"), dict) else {},
            services_by_id=services,
            receipt_path=result.receipt_path,
            generated_at=data.get("generatedAt"),
            warnings=list(result.warnings or []),
            errors=list(result.errors or []),
            duration_ms=result.duration_ms,
            fetched_at=now,
        )

    @staticmethod
    def _from_routes_result(command_id: str, result: RCCRunResult, now: float) -> FactoryTruthSnapshot:
        data = result.data if isinstance(result.data, dict) else {}
        routes = {}
        for route in data.get("routes", []) or []:
            if isinstance(route, dict) and route.get("id"):
                routes[route["id"]] = route
        return FactoryTruthSnapshot(
            command_id=command_id,
            verdict=result.verdict,
            ok=result.ok,
            routes_by_id=routes,
            receipt_path=result.receipt_path,
            generated_at=data.get("generatedAt"),
            warnings=list(result.warnings or []),
            errors=list(result.errors or []),
            duration_ms=result.duration_ms,
            fetched_at=now,
        )


_SERVICE: Optional[FactoryTruthService] = None


def get_factory_truth_service() -> FactoryTruthService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = FactoryTruthService()
    return _SERVICE
