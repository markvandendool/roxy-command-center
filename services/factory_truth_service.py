#!/usr/bin/env python3
"""
Factory Truth Service — GTK cache over the SSOT RCC DARK FACTORY commands.

This module contains no command logic. It delegates to RCCAdapter and gives the
GTK cockpit one normalized truth object for route badges, rail rows, and receipts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Dict, Optional

from services.rcc_adapter import RCCAdapter, RCCRunResult


@dataclass
class FactoryTruthSnapshot:
    verdict: str = "UNKNOWN"
    ready: Dict[str, bool] = field(default_factory=dict)
    services_by_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    routes_by_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    receipt_path: Optional[str] = None
    generated_at: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "ready": self.ready,
            "servicesById": self.services_by_id,
            "routesById": self.routes_by_id,
            "receiptPath": self.receipt_path,
            "generatedAt": self.generated_at,
            "warnings": self.warnings,
            "errors": self.errors,
            "durationMs": self.duration_ms,
        }


class FactoryTruthService:
    """Short-lived cache for factory.status and optional factory.routes."""

    def __init__(self, adapter: Optional[RCCAdapter] = None, ttl_seconds: float = 5.0):
        self.adapter = adapter or RCCAdapter()
        self.ttl_seconds = ttl_seconds
        self._last_status_at = 0.0
        self._snapshot = FactoryTruthSnapshot()

    def snapshot(self, *, force: bool = False) -> Dict[str, Any]:
        now = monotonic()
        if not force and now - self._last_status_at < self.ttl_seconds:
            return self._snapshot.as_dict()

        result = self.adapter.run("factory.status", receipt=True)
        self._snapshot = self._from_status_result(result)
        self._last_status_at = now
        return self._snapshot.as_dict()

    def route_doctor(self) -> Dict[str, Any]:
        result = self.adapter.run("factory.routes", receipt=True)
        routes = {}
        data = result.data if isinstance(result.data, dict) else {}
        for route in data.get("routes", []) or []:
            if isinstance(route, dict) and route.get("id"):
                routes[route["id"]] = route
        return {
            "verdict": result.verdict,
            "routesById": routes,
            "receiptPath": result.receipt_path,
            "warnings": result.warnings,
            "errors": result.errors,
            "durationMs": result.duration_ms,
            "raw": result.raw_json,
        }

    def _from_status_result(self, result: RCCRunResult) -> FactoryTruthSnapshot:
        data = result.data if isinstance(result.data, dict) else {}
        services = {}
        for service in data.get("services", []) or []:
            if isinstance(service, dict) and service.get("id"):
                services[service["id"]] = service
        return FactoryTruthSnapshot(
            verdict=result.verdict,
            ready=data.get("ready", {}) if isinstance(data.get("ready"), dict) else {},
            services_by_id=services,
            receipt_path=result.receipt_path,
            generated_at=data.get("generatedAt"),
            warnings=result.warnings,
            errors=result.errors,
            duration_ms=result.duration_ms,
        )


_SERVICE: Optional[FactoryTruthService] = None


def get_factory_truth_service() -> FactoryTruthService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = FactoryTruthService()
    return _SERVICE
