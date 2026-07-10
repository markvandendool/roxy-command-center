#!/usr/bin/env python3

from services.operator_kernel_client import build_action_packet, is_safe_action


def test_codex_integration_status_is_safe_read_only_action():
    assert is_safe_action("codex.integration.status")
    packet = build_action_packet(
        "codex.integration.status",
        {"includeLiveProbes": False},
    )
    assert packet["actionType"] == "codex.integration.status"
    assert packet["shell"]["platform"] == "hardware"
    assert packet["payload"]["includeLiveProbes"] is False
