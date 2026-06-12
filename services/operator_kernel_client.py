#!/usr/bin/env python3
"""
Operator Kernel Client — RCC bridge to MOSCore Operator Kernel action gateway.

Routes safe T0/T1 read-only actions through the gateway.
Never routes arbitrary shell, systemd mutation, or secrets.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, Optional

OPERATOR_KERNEL_GATEWAY_URL = "http://127.0.0.1:9135/api/operator/kernel/action"
REQUEST_TIMEOUT_S = 8.0

# Hardcoded safe action catalog — T0/T1 non-mutating only.
# Mirrors api/operator/kernel/action.mjs V1_ACTION_CATALOG.
V1_SAFE_ACTIONS = {
    "kernel.state.get",
    "kernel.sources.health",
    "kernel.capabilities.list",
    "kernel.receipts.list",
    "bridge.status.get",
    "agent.deck.status.get",
    "gas.status.get",
    "roxy.secondbrain.health.get",
    "roxy.secondbrain.score.get",
    "roxy.graph.memory.query",
    "roxy.context.packet.get",
    "roxy.command.center.snapshot.get",
    "roxy.daily.state.get",
    "roxy.benchmark.latest.get",
    "roxy.judge.report.latest.get",
    "warmup.status.get",
    "specialist.route.request",
    "graph.query",
    "squad.form.request",
    "judge.review.request",
    "efficiency.report.request",
    "backlog.candidates.request",
    "composer.run.request",
    "promotion.queue.request",
    "institutional.metrics.request",
    "proposal.verdict.request",
    "proposal.quality.request",
    "luno.economics.read",
}


def is_safe_action(action_type: str) -> bool:
    """Return True if action_type is in the safe V1 catalog."""
    return action_type in V1_SAFE_ACTIONS


def build_action_packet(
    action_type: str,
    payload: Optional[Dict[str, Any]] = None,
    shell_meta: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build an ActionPacket matching the Operator Kernel schema."""
    import time
    action_id = f"rcc-{int(time.time() * 1000)}-{hash(action_type) & 0xFFFFFF:06x}"
    shell = {
        "platform": "hardware",
        "deviceId": "roxy-native-gtk4",
        "shellVersion": "2020e4fe71ec",
        "surfaceId": "rcc-main",
    }
    if shell_meta:
        shell.update(shell_meta)
    timestamp = datetime.now().isoformat()
    return {
        # Existing Operator Kernel wire shape.
        "actionId": action_id,
        "actionType": action_type,
        "version": "1.0.0",
        "timestamp": timestamp,
        "shell": shell,
        "payload": payload or {},
        # Compatibility aliases for local smoke tests and older callers. These
        # are stripped before the packet is POSTed to the gateway.
        "id": action_id,
        "action": action_type,
        "requestedAt": timestamp,
    }


def _gateway_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the existing Operator Kernel gateway fields."""
    return {
        "actionId": packet["actionId"],
        "actionType": packet["actionType"],
        "version": packet["version"],
        "timestamp": packet["timestamp"],
        "shell": packet["shell"],
        "payload": packet["payload"],
    }


def send_action_packet(
    action_type: str,
    payload: Optional[Dict[str, Any]] = None,
    shell_meta: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    POST an ActionPacket to the Operator Kernel gateway.
    Returns the GatewayResponse dict.
    Raises ValueError if action is not safe.
    """
    if not is_safe_action(action_type):
        raise ValueError(f"Action '{action_type}' is not in the safe V1 catalog")

    packet = build_action_packet(action_type, payload, shell_meta)
    body = json.dumps(_gateway_packet(packet)).encode("utf-8")

    req = urllib.request.Request(
        OPERATOR_KERNEL_GATEWAY_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body_text = exc.read().decode("utf-8")
            return json.loads(body_text)
        except Exception:
            return {
                "ok": False,
                "error": f"HTTP {exc.code}: {exc.reason}",
                "receipt": None,
            }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "receipt": None,
        }


def request_receipt(
    action_type: str,
    payload: Optional[Dict[str, Any]] = None,
    shell_meta: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Send a safe action and return only the receipt dict (or None on failure).
    """
    response = send_action_packet(action_type, payload, shell_meta)
    return response.get("receipt")


if __name__ == "__main__":
    # Smoke test — call a safe T0 action
    print("[OK-Client] Smoke test: kernel.state.get")
    result = send_action_packet("kernel.state.get")
    print(json.dumps(result, indent=2, default=str))
