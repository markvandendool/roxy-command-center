#!/usr/bin/env python3
"""
Operator Kernel Receipt Bridge — Dual-write RCC receipts into MOSCore ledger.

RCC keeps its own local receipts (roxy-command-center-action.v1).
This bridge appends a normalized Operator Kernel-style receipt to the
shared MOSCore ledger so the Operator Kernel and graph runtime can see
RCC actions in the unified action stream.

Target ledger: output/operator-kernel/action-receipts.ndjson (same as gateway).
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# MindSong SSOT root — same path used by receipts_proof_page.py
SSOT_ROOT = Path("/mnt/work/ssot/mindsong-juke-hub")
OPERATOR_KERNEL_LEDGER_PATH = SSOT_ROOT / "output" / "operator-kernel" / "action-receipts.ndjson"

# Feature flag — can be disabled via env var if bridge causes issues.
BRIDGE_ENABLED = os.environ.get("RCC_RECEIPT_BRIDGE_ENABLED", "1") == "1"

# Map RCC action names to synthetic OK tiers.
# All RCC actions are native; they do not exist in the OK catalog.
# We treat them as T1 (operator-initiated, non-destructive).
RCC_ACTION_TIERS: Dict[str, str] = {
    "kimi_assign": "T1",
    "voice_speak": "T1",
    "voice_command": "T1",
    "voice_status": "T0",
    "voice_unknown": "T0",
    "judge_mission": "T1",
    "investigate": "T1",
}


def _ensure_ledger_dir():
    OPERATOR_KERNEL_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)


def _build_operator_kernel_receipt(rcc_receipt: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert an RCC receipt (roxy-command-center-action.v1) into an
    Operator Kernel ActionReceipt shape.
    """
    action = rcc_receipt.get("action", "unknown")
    mission_id = rcc_receipt.get("missionId", "")
    status = rcc_receipt.get("status", "unknown")
    error = rcc_receipt.get("error", "")

    # Derive outcome from RCC status
    if status in ("completed",):
        outcome = "success"
    elif status in ("failed",):
        outcome = "error"
    elif status in ("blocked",):
        outcome = "denied"
    else:
        outcome = "success"  # queued / pending / in-progress default

    detail = f"RCC {action}: {status}"
    if mission_id:
        detail += f" | mission={mission_id}"
    if error:
        detail += f" | error={error}"

    receipt_id = f"rcpt-rcc-{int(datetime.now().timestamp() * 1000)}-{hash(action) & 0xFFFFFF:06x}"
    action_id = f"rcc-act-{hash(mission_id or action) & 0xFFFFFFFF:08x}"

    return {
        "schemaVersion": "operator-kernel-action-receipt.bridged.v1",
        "receiptId": receipt_id,
        "actionId": action_id,
        "actionType": f"rcc.{action}",
        "timestamp": datetime.now().isoformat(),
        "shell": {
            "platform": "roxy-command-center",
            "deviceId": "roxy-native-gtk4",
            "shellVersion": "2020e4fe71ec",
            "surfaceId": "rcc-main",
        },
        "policy": {
            "allowed": True,
            "tier": RCC_ACTION_TIERS.get(action, "T1"),
            "reason": "RCC native action, bridged to Operator Kernel ledger",
            "denialCode": None,
        },
        "execution": {
            "outcome": outcome,
            "detail": detail,
            "resultData": {
                "missionId": mission_id,
                "missionTitle": rcc_receipt.get("missionTitle", ""),
                "targetAgent": rcc_receipt.get("targetAgent", ""),
                "targetLane": rcc_receipt.get("targetLane", ""),
                "authority": rcc_receipt.get("authority", "operator"),
            },
            "error": error or None,
        },
        "payload": rcc_receipt.get("payload", {}),
        "rccSource": {
            "schemaVersion": rcc_receipt.get("schemaVersion", "roxy-command-center-action.v1"),
            "receiptPath": rcc_receipt.get("receiptPath", ""),
        },
    }


def append_to_operator_kernel_ledger(rcc_receipt: Dict[str, Any]) -> bool:
    """
    Bridge an RCC receipt into the Operator Kernel ledger.
    Returns True on success, False on failure (never raises).
    """
    if not BRIDGE_ENABLED:
        print("[OK-Bridge] Bridge disabled via RCC_RECEIPT_BRIDGE_ENABLED")
        return False

    try:
        _ensure_ledger_dir()
        ok_receipt = _build_operator_kernel_receipt(rcc_receipt)
        line = json.dumps(ok_receipt, separators=(",", ":"), default=str) + "\n"
        with open(OPERATOR_KERNEL_LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(line)
        print(f"[OK-Bridge] Appended to ledger: {OPERATOR_KERNEL_LEDGER_PATH}")
        return True
    except Exception as exc:
        print(f"[OK-Bridge] Failed to append to ledger: {exc}")
        return False


def dual_write_receipt(rcc_receipt: Dict[str, Any]) -> bool:
    """Convenience alias."""
    return append_to_operator_kernel_ledger(rcc_receipt)


if __name__ == "__main__":
    # Smoke test
    test_receipt = {
        "schemaVersion": "roxy-command-center-action.v1",
        "action": "kimi_assign",
        "missionId": "smoke-test",
        "missionTitle": "Smoke Test Mission",
        "source": "roxy-command-center",
        "requestedAt": datetime.now().isoformat(),
        "status": "completed",
        "targetAgent": "kimi-captain",
        "targetLane": "mainline",
        "authority": "operator",
        "receiptPath": "/tmp/smoke.json",
        "payload": {"task": "verify bridge"},
        "error": "",
        "nextAction": "",
    }
    ok = append_to_operator_kernel_ledger(test_receipt)
    print(f"Smoke test result: {ok}")
