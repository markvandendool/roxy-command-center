#!/usr/bin/env python3
"""
Investigation Service — Create read-only investigation packets.

Schema: investigation-packet.v1
Safe: no mutations, only bounded read queries.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from services.action_receipt_service import write_action_receipt

PACKET_DIR = Path(__file__).parent.parent / "output" / "roxy-command-center" / "investigations"


def _ensure_dir():
    PACKET_DIR.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now().isoformat()


def create_investigation_packet(
    mission_id: str,
    mission_title: str,
    question: str,
    source_artifacts: list = None,
    allowed_read_paths: list = None,
    expected_output: str = "",
    deadline_hours: int = 24,
) -> Dict[str, Any]:
    """Create a read-only investigation packet and receipt."""
    _ensure_dir()

    packet_id = f"investigate-{uuid.uuid4().hex[:12]}"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    packet = {
        "schemaVersion": "investigation-packet.v1",
        "packetId": packet_id,
        "missionId": mission_id,
        "missionTitle": mission_title,
        "question": question,
        "sourceArtifacts": source_artifacts or [],
        "allowedReadPaths": allowed_read_paths or [
            "docs/",
            "public/roxy/",
            "output/",
            "scripts/",
        ],
        "forbiddenPaths": [
            "config/secrets/",
            ".env*",
            "*.key",
            "*.pem",
        ],
        "expectedOutput": expected_output or "Summary of findings with evidence citations",
        "deadlineHours": deadline_hours,
        "status": "queued",
        "createdAt": _ts(),
        "safeMode": True,
        "mutationAllowed": False,
    }

    path = PACKET_DIR / f"{ts}-{packet_id}.json"
    path.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")

    # Write action receipt
    receipt_path = write_action_receipt(
        action="investigate",
        mission_id=mission_id,
        mission_title=mission_title,
        status="queued",
        target_agent="regent-investigator",
        target_lane="read-only",
        authority="operator",
        payload={
            "packetId": packet_id,
            "packetPath": str(path),
            "questionPreview": question[:200],
            "safeMode": True,
        },
        next_action="queue for read-only investigation",
    )

    print(f"[Investigation] Packet {packet_id} created")
    return {
        "packet": packet,
        "packetPath": str(path),
        "receiptPath": str(receipt_path),
    }


def list_investigations(limit: int = 20) -> list:
    """List recent investigation packets."""
    _ensure_dir()
    files = sorted(PACKET_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    packets = []
    for f in files[:limit]:
        try:
            packets.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return packets
