#!/usr/bin/env python3
"""
MOS cockpit service for the Phase2C review build.

This is a thin client over existing MOS ingress/authority endpoints. It does
not start services, own bindings, store credentials, or create another control
bus.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.roxy_status_provider import snapshot as roxy_snapshot


INGRESS_BASE = "http://127.0.0.1:49172"
AUTHORITY_BASE = "http://127.0.0.1:49173"
LEDGER_PATH = Path(
    os.environ.get(
        "ROXY_COCKPIT_LEDGER_PATH",
        str(Path.home() / ".cache" / "roxy-command-center" / "phase2c-result-ledger.jsonl"),
    )
)
LEDGER_LIMIT = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], timeout: int = 4) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "stdout": "", "stderr": ""}


def _safe_text(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:limit]
    try:
        return json.dumps(value, sort_keys=True)[:limit]
    except Exception:
        return str(value)[:limit]


def _redact_text(value: str, token: str = "") -> str:
    redacted = value
    if token:
        redacted = redacted.replace(token, "[redacted-token]")
    return redacted.replace("x-ingress-token", "x-ingress-token:[redacted]")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp_path.open("w") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        pass


def _sanitize_ledger_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    secret_values = {
        str(row.get("token"))
        for row in rows
        if isinstance(row.get("token"), str) and row.get("token")
    }
    sanitized_rows: list[dict[str, Any]] = []
    for row in rows:
        clean: dict[str, Any] = {}
        for key, value in row.items():
            if key.lower() == "token":
                continue
            if isinstance(value, str):
                redacted = value
                for secret in secret_values:
                    redacted = redacted.replace(secret, "[redacted-token]")
                clean[key] = _redact_text(redacted)
            else:
                clean[key] = value
        sanitized_rows.append(clean)
    return sanitized_rows


def _headers(token: str = "") -> dict[str, str]:
    headers = {
        "content-type": "application/json",
        "accept": "application/json",
    }
    if token:
        headers["x-ingress-token"] = token
    return headers


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str = "",
    timeout: float = 1.5,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method, headers=_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
            return {
                "ok": 200 <= res.status < 300,
                "status": res.status,
                "url": url,
                "data": parsed,
                "bodySummary": _safe_text(parsed),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"sample": raw[:400]}
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "data": parsed,
            "error": parsed.get("error") if isinstance(parsed, dict) else str(exc),
            "bodySummary": _safe_text(parsed),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "url": url,
            "data": {},
            "error": str(exc),
            "bodySummary": "",
        }


def controlled_roxy_status_payload() -> dict[str, Any]:
    return {
        "eventType": "button",
        "deviceId": "roxy-command-center",
        "buttonId": "ui:roxy-status",
        "sourceType": "http-shortcut",
        "actionId": "system.status.query",
        "target": "roxy",
    }


def _ledger_rows(limit: int = LEDGER_LIMIT) -> list[dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = LEDGER_PATH.read_text(errors="replace").splitlines()
    except Exception:
        return []
    for line in lines:
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows[-limit:]


def _append_ledger(entry: dict[str, Any]) -> bool:
    try:
        rows = _ledger_rows(LEDGER_LIMIT - 1)
        rows.append(dict(entry))
        sanitized_rows = _sanitize_ledger_rows(rows)[-LEDGER_LIMIT:]
        text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in sanitized_rows)
        _atomic_write_text(LEDGER_PATH, text)
        return True
    except Exception:
        return False


def read_local_ledger(limit: int = 50) -> list[dict[str, Any]]:
    return list(reversed(_ledger_rows(limit)))


def listener_status() -> str:
    return _run(["bash", "-lc", "ss -ltnp | grep -E ':49170|:49172|:49173|:9135|:19135' || true"]).get("stdout", "")


def fetch_bindings(token: str = "") -> dict[str, Any]:
    primary = request_json(f"{AUTHORITY_BASE}/bindings", token=token)
    if primary.get("ok"):
        return {**primary, "route": "/bindings"}
    fallback = request_json(f"{AUTHORITY_BASE}/api/bindings", token=token)
    return {**fallback, "route": "/api/bindings"}


def snapshot(token: str = "", *, include_provider: bool = True) -> dict[str, Any]:
    ingress_health = request_json(f"{INGRESS_BASE}/healthz")
    authority_health = request_json(f"{AUTHORITY_BASE}/healthz")
    events = request_json(f"{INGRESS_BASE}/api/events/recent?limit=50", token=token)
    results = request_json(f"{INGRESS_BASE}/api/results/recent?limit=50", token=token)
    bindings = fetch_bindings(token)

    data: dict[str, Any] = {
        "generatedAt": _now(),
        "ingress": {
            "baseUrl": INGRESS_BASE,
            "health": ingress_health,
            "events": events,
            "results": results,
            "routeStatus": {
                "inputEvent": "/api/input-event",
                "controlAlias": "/api/control/input",
                "stream": "ws://127.0.0.1:49172/stream",
                "recentEvents": "/api/events/recent",
                "inputResult": "/api/input-result",
                "recentResults": "/api/results/recent",
            },
        },
        "authority": {
            "baseUrl": AUTHORITY_BASE,
            "health": authority_health,
            "bindings": bindings,
        },
        "listeners": listener_status(),
        "localLedger": {
            "path": str(LEDGER_PATH),
            "entries": read_local_ledger(),
            "sessionOnlyToken": True,
        },
        "payloadPreview": controlled_roxy_status_payload(),
    }

    if include_provider:
        try:
            data["roxyStatus"] = roxy_snapshot()
        except Exception as exc:
            data["roxyStatus"] = {"ok": False, "error": str(exc)}
    return data


def send_roxy_status_query(token: str = "") -> dict[str, Any]:
    health = request_json(f"{INGRESS_BASE}/healthz")
    routes = health.get("data", {}).get("routes", {}) if isinstance(health.get("data"), dict) else {}
    aliases = routes.get("aliases") if isinstance(routes, dict) else []
    route = "/api/control/input" if "/api/control/input" in aliases else "/api/input-event"
    payload = controlled_roxy_status_payload()
    response = request_json(f"{INGRESS_BASE}{route}", method="POST", payload=payload, token=token, timeout=2.5)
    entry = {
        "createdAt": _now(),
        "source": "Phase2C MOS Cockpit",
        "operation": "Roxy Status Query",
        "route": route,
        "requestSummary": "roxy-command-center/ui:roxy-status -> system.status.query target=roxy",
        "responseStatus": response.get("status"),
        "responseBodySummary": _redact_text(response.get("bodySummary", ""), token),
        "eventId": response.get("data", {}).get("eventId") if isinstance(response.get("data"), dict) else None,
        "actionId": "system.status.query",
        "target": "roxy",
        "success": bool(response.get("ok") and response.get("data", {}).get("ok", True)),
        "failureReason": response.get("error") or response.get("data", {}).get("error") if isinstance(response.get("data"), dict) else response.get("error"),
    }
    ledger_written = _append_ledger(entry)
    return {"request": payload, "route": route, "response": response, "ledgerEntry": entry, "ledgerWritten": ledger_written}
