#!/usr/bin/env python3
"""
Kimi Assignment Service — Create assignment packets for Kimi long-runner or visible terminal.

Schema: kimi-assignment-packet.v1
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from services.action_receipt_service import write_action_receipt, update_receipt_status

PACKET_DIR = Path(__file__).parent.parent / "output" / "roxy-command-center" / "kimi-assignments"


def _ensure_dir():
    PACKET_DIR.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now().isoformat()


def create_assignment_packet(
    mission_id: str,
    mission_title: str,
    brief: str,
    allowed_paths: list = None,
    forbidden_paths: list = None,
    required_proof: list = None,
    target_agent: str = "kimi",
    target_surface: str = "auto",  # auto | visible-terminal | long-runner
) -> Dict[str, Any]:
    """Create a Kimi assignment packet and receipt."""
    _ensure_dir()

    packet_id = f"kimi-assign-{uuid.uuid4().hex[:12]}"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Determine target surface
    visible_terminal = _discover_visible_terminal()
    if visible_terminal:
        target_surface = "visible-terminal"
        target_agent = visible_terminal
    else:
        target_surface = "long-runner"
        target_agent = "mindsong-long-runner"

    packet = {
        "schemaVersion": "kimi-assignment-packet.v1",
        "packetId": packet_id,
        "missionId": mission_id,
        "missionTitle": mission_title,
        "brief": brief,
        "allowedPaths": allowed_paths or ["docs/", "src/", "scripts/", "output/"],
        "forbiddenPaths": forbidden_paths or ["config/secrets/", ".env*", "*.key"],
        "requiredProof": required_proof or ["receipt", "diff"],
        "targetAgent": target_agent,
        "targetSurface": target_surface,
        "status": "queued",
        "createdAt": _ts(),
        "queuedAt": _ts(),
    }

    path = PACKET_DIR / f"{ts}-{packet_id}.json"
    path.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")

    # Write action receipt
    receipt_path = write_action_receipt(
        action="kimi_assign",
        mission_id=mission_id,
        mission_title=mission_title,
        status="queued",
        target_agent=target_agent,
        target_lane=target_surface,
        authority="operator",
        payload={"packetId": packet_id, "packetPath": str(path), "briefPreview": brief[:200]},
        next_action=f"dispatch to {target_surface}",
    )

    print(f"[KimiAssignment] Packet {packet_id} -> {target_surface}")
    return {
        "packet": packet,
        "packetPath": str(path),
        "receiptPath": str(receipt_path),
    }


def _discover_visible_terminal() -> Optional[str]:
    """Check if a visible Kimi terminal is available."""
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", "kimi"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return "kimi-terminal"
    except Exception:
        pass
    return None


def list_assignments(limit: int = 20) -> list:
    """List recent assignment packets."""
    _ensure_dir()
    files = sorted(PACKET_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    packets = []
    for f in files[:limit]:
        try:
            packets.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return packets
