#!/usr/bin/env python3
"""
Friday status provider.

Reads the deployed Friday `rcc-status` JSON with a bounded timeout. It does not
probe secrets, mutate services, or treat cached local state as sole authority.
"""

import json
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.profile_config import load_profile


SECRET_KEYS = ("secret", "token", "password", "apiKey", "api_key", "authorization")
DEFAULT_TIMEOUT_S = 8.0
FRESH_SECONDS = 180
STALE_SECONDS = 900


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if any(marker.lower() in key.lower() for marker in SECRET_KEYS):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _freshness(generated_at: Any, now: Optional[datetime] = None) -> str:
    parsed = _parse_timestamp(generated_at)
    if parsed is None:
        return "unknown"
    now = now or datetime.now(timezone.utc)
    age_seconds = max(0.0, (now - parsed).total_seconds())
    if age_seconds <= FRESH_SECONDS:
        return "fresh"
    if age_seconds <= STALE_SECONDS:
        return "stale"
    return "unknown"


def collect_friday_status(profile_name: str = "friday", timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    profile = load_profile(profile_name)
    command = profile.get("statusCommand") or "/home/mark/bin/rcc-status"

    try:
        cp = subprocess.run(
            [command],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "sourceAuthority": False,
            "freshness": "unknown",
            "error": "status command timed out",
        }
    except Exception as exc:
        return {
            "ok": False,
            "sourceAuthority": False,
            "freshness": "unknown",
            "error": str(exc),
        }

    if cp.returncode != 0:
        return {
            "ok": False,
            "sourceAuthority": False,
            "freshness": "unknown",
            "error": cp.stderr.strip() or f"status command exited {cp.returncode}",
        }

    try:
        raw = json.loads(cp.stdout)
    except Exception as exc:
        return {
            "ok": False,
            "sourceAuthority": False,
            "freshness": "unknown",
            "error": f"invalid JSON: {exc}",
        }

    data = _redact(raw)
    bridge = data.get("bridge") or {}
    services = data.get("services") or []

    return {
        "ok": True,
        "sourceAuthority": False,
        "freshness": _freshness(data.get("generatedAt")),
        "host": data.get("host"),
        "generatedAt": data.get("generatedAt"),
        "disk": data.get("disk"),
        "failedUnits": data.get("failedUnits") or [],
        "failedUnitCount": len(data.get("failedUnits") or []),
        "bridge": {
            "headMatch": bridge.get("headMatch"),
            "repoHead": bridge.get("repoHead"),
            "bridgeBuildHead": bridge.get("bridgeBuildHead"),
            "generatedAt": bridge.get("generatedAt"),
            "note": bridge.get("note"),
        },
        "services": services,
        "operatorHealth": data.get("operatorHealth") or {},
        "raw": data,
    }


if __name__ == "__main__":
    print(json.dumps(collect_friday_status(), indent=2, default=str))
