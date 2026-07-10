#!/usr/bin/env python3
"""Pure classification tests for native RCC process health."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import tools.runtime_check as runtime_check

from tools.runtime_check import APP_ROOT, classify_native_health, is_expected_primary


def base_report():
    return {
        "processAlive": True,
        "primaryIdentityValid": True,
        "windowProbeAvailable": True,
        "visibleWindowCount": 1,
        "backendStatuses": {"kernel": {"ok": True}},
        "lastTraceback": None,
    }


def test_named_health_states():
    report = base_report()
    assert classify_native_health(report) == "RCC_NATIVE_HEALTHY"

    report["backendStatuses"]["kernel"]["ok"] = False
    assert classify_native_health(report) == "RCC_BACKEND_DEGRADED"

    report = base_report()
    report["visibleWindowCount"] = 0
    assert classify_native_health(report) == "RCC_STALE_PRIMARY_NO_WINDOW"

    report["visibleWindowCount"] = 2
    assert classify_native_health(report) == "RCC_MULTIPLE_WINDOWS"

    report = base_report()
    report["processAlive"] = False
    assert classify_native_health(report) == "RCC_PROCESS_MISSING"
    report["lastTraceback"] = {"excerpt": "Traceback"}
    assert classify_native_health(report) == "RCC_STARTUP_EXCEPTION"


def test_primary_identity_requires_exact_uid_cwd_executable_and_main():
    identity = {
        "alive": True,
        "uid": os.getuid(),
        "cwd": str(APP_ROOT),
        "executable": "/usr/bin/python3.12",
        "argv": ["python3", "-X", "faulthandler", "-u", "main.py"],
    }
    assert is_expected_primary(identity)

    for field, value in (
        ("uid", os.getuid() + 1),
        ("cwd", "/tmp/not-rcc"),
        ("executable", "/usr/bin/node"),
        ("argv", ["python3", "other.py"]),
    ):
        altered = dict(identity)
        altered[field] = value
        assert not is_expected_primary(altered)


def launch_health(window_count=1):
    return {
        "processAlive": True,
        "primaryIdentityValid": True,
        "windowProbeAvailable": True,
        "visibleWindowCount": window_count,
        "dbusOwnerPid": 4242,
        "sourceCommit": "abc123",
    }


def test_prepare_launch_is_fail_closed_and_exact_pid_scoped():
    receipt_path = Path("/tmp/rcc-test-launch-receipt.json")
    with (
        patch.object(runtime_check, "native_health_report", return_value=launch_health()),
        patch.object(runtime_check, "activate_primary", return_value={"ok": True}),
        patch.object(runtime_check, "write_launch_receipt", return_value=receipt_path),
    ):
        report, code = runtime_check.prepare_launch()
        assert code == 10
        assert report["outcome"] == "EXISTING_PRIMARY_PRESENTED"

    with (
        patch.object(runtime_check, "native_health_report", return_value=launch_health()),
        patch.object(runtime_check, "activate_primary", return_value={"ok": False, "error": "denied"}),
        patch.object(runtime_check, "write_launch_receipt", return_value=receipt_path),
    ):
        report, code = runtime_check.prepare_launch()
        assert code == 6
        assert report["status"] == "RCC_ACTIVATION_FAILED"

    stale = launch_health(window_count=0)
    with (
        patch.object(runtime_check, "native_health_report", return_value=stale),
        patch.object(runtime_check, "terminate_exact_primary", return_value={"terminated": True, "signal": "SIGTERM"}) as terminate,
        patch.object(runtime_check, "write_launch_receipt", return_value=receipt_path),
        patch.object(Path, "write_text"),
    ):
        report, code = runtime_check.prepare_launch()
        assert code == 0
        assert report["outcome"] == "RECOVERED_START_REQUIRED"
        terminate.assert_called_once_with(4242)


def main() -> int:
    test_named_health_states()
    test_primary_identity_requires_exact_uid_cwd_executable_and_main()
    test_prepare_launch_is_fail_closed_and_exact_pid_scoped()
    print("RCC_NATIVE_RUNTIME_HEALTH_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
