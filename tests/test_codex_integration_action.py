#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.operator_kernel_client import APP_ROOT, build_action_packet, is_safe_action


def test_codex_integration_status_is_safe_read_only_action():
    assert is_safe_action("codex.integration.status")
    packet = build_action_packet(
        "codex.integration.status",
        {"includeLiveProbes": False},
    )
    assert packet["actionType"] == "codex.integration.status"
    expected_head = os.getenv("RCC_SOURCE_COMMIT") or subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=APP_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert packet["shell"]["platform"] == "hardware"
    assert packet["shell"]["shellVersion"] == expected_head
    assert packet["payload"]["includeLiveProbes"] is False


def main() -> int:
    test_codex_integration_status_is_safe_read_only_action()
    print("RCC_CODEX_INTEGRATION_ACTION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
