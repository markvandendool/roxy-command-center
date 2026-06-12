#!/usr/bin/env python3
"""
Smoke tests for the read-only Friday profile.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.profile_config import load_profile, profile_allows_page
from services.operator_kernel_client import build_action_packet
from services.rcc_command_kernel_adapter import is_allowed_command


profile = load_profile("friday")
assert profile["sourceAuthority"] is False
assert "terminal" in profile["disabledPages"]
assert not profile_allows_page(profile, "terminal")
assert profile_allows_page(profile, "overview")
print("PROFILE_OK")

packet = build_action_packet("kernel.state.get")
assert packet["action"] == "kernel.state.get"
assert packet["actionType"] == "kernel.state.get"
assert "id" in packet
assert "actionId" in packet
assert "requestedAt" in packet
assert "timestamp" in packet
print("ACTION_PACKET_OK")

assert is_allowed_command("roxy.status")
assert not is_allowed_command("arbitrary-shell")
assert not is_allowed_command("roxy.status; rm -rf /")
print("RCC_ADAPTER_POLICY_OK")
