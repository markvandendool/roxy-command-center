#!/usr/bin/env python3
"""
Operator Kernel Alert Bridge — Dual-write RCC alerts into MOSCore attention ledger.

RCC keeps its own local alerts (~/.local/share/roxy-command-center/alerts.jsonl).
This bridge appends a normalized attention record to a shared MOSCore ledger
so the Operator Kernel and command center surfaces can see RCC alerts.

Target ledger: /mnt/work/ssot/mindsong-juke-hub/output/operator-kernel/attention-alerts.ndjson
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

SSOT_ROOT = Path("/mnt/work/ssot/mindsong-juke-hub")
ATTENTION_LEDGER_PATH = SSOT_ROOT / "output" / "operator-kernel" / "attention-alerts.ndjson"

BRIDGE_ENABLED = os.environ.get("RCC_ALERT_BRIDGE_ENABLED", "1") == "1"

SEVERITY_MAP = {
    "info": "info",
    "warning": "warning",
    "critical": "critical",
}

STATUS_MAP = {
    True: "resolved",
    False: "open",
}


def _ensure_ledger_dir():
    ATTENTION_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)


def _build_attention_alert(rcc_alert_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert an RCC alert log entry into an Operator Kernel attention record.
    RCC alert entry schema (from alert_manager.py _log_alert):
      { id, type, severity, title, message, source, timestamp, cleared, clear_timestamp }
    """
    alert_id = rcc_alert_entry.get("id", "")
    severity = SEVERITY_MAP.get(rcc_alert_entry.get("severity", "").lower(), "info")
    cleared = rcc_alert_entry.get("cleared", False)
    status = STATUS_MAP.get(cleared, "open")
    ts_raw = rcc_alert_entry.get("timestamp")
    ts = datetime.fromtimestamp(ts_raw).isoformat() if isinstance(ts_raw, (int, float)) else datetime.now().isoformat()

    return {
        "schemaVersion": "operator-kernel-attention-alert.bridged.v1",
        "alertId": f"rcc-attn-{alert_id}",
        "timestamp": ts,
        "source": {
            "system": "roxy-command-center",
            "host": "roxy",
            "repo": "/mnt/work/roxy-core/apps/roxy-command-center-review",
        },
        "severity": severity,
        "status": status,
        "title": rcc_alert_entry.get("title", ""),
        "detail": rcc_alert_entry.get("message", ""),
        "category": rcc_alert_entry.get("type", ""),
        "rccSource": {
            "alertId": alert_id,
            "alertType": rcc_alert_entry.get("type", ""),
            "sourceLabel": rcc_alert_entry.get("source", ""),
            "cleared": cleared,
            "clearTimestamp": rcc_alert_entry.get("clear_timestamp"),
        },
    }


def append_to_attention_ledger(rcc_alert_entry: Dict[str, Any]) -> bool:
    """
    Bridge an RCC alert entry into the MOSCore attention ledger.
    Returns True on success, False on failure (never raises).
    """
    if not BRIDGE_ENABLED:
        print("[OK-Alert-Bridge] Bridge disabled via RCC_ALERT_BRIDGE_ENABLED")
        return False

    try:
        _ensure_ledger_dir()
        ok_alert = _build_attention_alert(rcc_alert_entry)
        line = json.dumps(ok_alert, separators=(",", ":"), default=str) + "\n"
        with open(ATTENTION_LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(line)
        print(f"[OK-Alert-Bridge] Appended to attention ledger: {ATTENTION_LEDGER_PATH}")
        return True
    except Exception as exc:
        print(f"[OK-Alert-Bridge] Failed to append to attention ledger: {exc}")
        return False


def bridge_alert(
    alert_id: str,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    source: str = "",
    timestamp: Optional[float] = None,
    cleared: bool = False,
    clear_timestamp: Optional[float] = None,
) -> bool:
    """Convenience wrapper that builds RCC-style entry and bridges it."""
    entry = {
        "id": alert_id,
        "type": alert_type,
        "severity": severity,
        "title": title,
        "message": message,
        "source": source,
        "timestamp": timestamp or datetime.now().timestamp(),
        "cleared": cleared,
        "clear_timestamp": clear_timestamp,
    }
    return append_to_attention_ledger(entry)


if __name__ == "__main__":
    ok = bridge_alert(
        alert_id="smoke-test-alert",
        alert_type="service_down",
        severity="warning",
        title="Smoke Alert",
        message="RCC alert convergence smoke test",
        source="alert-bridge-smoke",
    )
    print(f"Smoke test result: {ok}")
