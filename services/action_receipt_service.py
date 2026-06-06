#!/usr/bin/env python3
"""
Action Receipt Service — Unified receipt writer for all operator actions.

Every button click in the Command Center that represents a real action
must produce a receipt. No button is merely a dialog.

Schema: roxy-command-center-action.v1
"""

import json
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from services.operator_kernel_receipt_bridge import dual_write_receipt

RECEIPT_DIR = Path(__file__).parent.parent / "output" / "roxy-command-center" / "actions"


def _ensure_dir():
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now().isoformat()


def write_action_receipt(
    action: str,
    mission_id: str,
    mission_title: str,
    status: str,  # queued | pending | completed | blocked | failed
    target_agent: str = "",
    target_lane: str = "",
    authority: str = "operator",
    payload: Optional[Dict[str, Any]] = None,
    error: str = "",
    next_action: str = "",
) -> Path:
    """Write a canonical action receipt to disk."""
    _ensure_dir()

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_id = hashlib.sha256(f"{action}-{mission_id}-{ts}-{uuid.uuid4()}".encode()).hexdigest()[:8]
    filename = f"{ts}-{action}-{short_id}.json"
    path = RECEIPT_DIR / filename

    receipt = {
        "schemaVersion": "roxy-command-center-action.v1",
        "action": action,
        "missionId": mission_id,
        "missionTitle": mission_title,
        "source": "roxy-command-center",
        "requestedAt": _ts(),
        "status": status,
        "targetAgent": target_agent,
        "targetLane": target_lane,
        "authority": authority,
        "receiptPath": str(path),
        "payload": payload or {},
        "error": error,
        "nextAction": next_action,
    }

    path.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(f"[ActionReceipt] Written: {path}")
    dual_write_receipt(receipt)
    return path


def update_receipt_status(receipt_path: Path, status: str, payload: Optional[Dict[str, Any]] = None, error: str = ""):
    """Update an existing receipt's status."""
    try:
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        data["status"] = status
        data["updatedAt"] = _ts()
        if payload:
            data["payload"] = {**data.get("payload", {}), **payload}
        if error:
            data["error"] = error
        receipt_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"[ActionReceipt] Updated: {receipt_path} -> {status}")
    except Exception as exc:
        print(f"[ActionReceipt] Update failed: {exc}")


def list_receipts(limit: int = 100) -> list:
    """List recent action receipts, newest first."""
    _ensure_dir()
    files = sorted(RECEIPT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    receipts = []
    for f in files[:limit]:
        try:
            receipts.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return receipts


def get_recent_by_action(action: str, limit: int = 10) -> list:
    """Get recent receipts for a specific action type."""
    return [r for r in list_receipts(limit=limit * 5) if r.get("action") == action][:limit]
