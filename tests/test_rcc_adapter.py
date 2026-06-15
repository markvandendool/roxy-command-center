#!/usr/bin/env python3
"""
RCC Adapter Smoke Test — Verifies RCC Command Kernel integration.

Run:
    python3 tests/test_rcc_adapter.py

Expected: RCC_GTK4_ADAPTER_SMOKE_PASS
"""

import sys
import os
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.rcc_adapter import RCCAdapter


def test_adapter_status():
    """RCC CLI must exist."""
    adapter = RCCAdapter()
    status = adapter.status()
    assert status["ssot_root_exists"], "SSOT root missing"
    assert status["rcc_cli_exists"], "RCC CLI missing"
    print("✅ adapter_status")


def test_list_commands():
    """Must discover all 6 P0 commands."""
    adapter = RCCAdapter()
    cmds = adapter.list_commands()
    ids = [c.id for c in cmds]
    expected = [
        "roxy.status",
        "roxy.resources",
        "roxy.models",
        "agent.agents",
        "proof.doctor",
        "proof.receipts",
    ]
    for e in expected:
        assert e in ids, f"Missing command: {e}"
    print(f"✅ list_commands ({len(cmds)} commands)")


def test_dry_run_all():
    """Dry-run every command. Must not fail."""
    adapter = RCCAdapter()
    cmds = adapter.list_commands()
    for meta in cmds:
        result = adapter.run(meta.id, dry_run=True)
        assert result.ok, f"Dry-run failed for {meta.id}: {result.errors}"
        print(f"  ✅ dry-run {meta.id} -> {result.verdict}")
    print("✅ dry_run_all")


def test_run_t0_commands():
    """Run all T0 commands. Must return valid results."""
    adapter = RCCAdapter()
    cmds = adapter.list_commands()
    for meta in cmds:
        if meta.risk_tier != "T0":
            continue
        result = adapter.run(meta.id, receipt=True)
        assert isinstance(result.verdict, str) and result.verdict, f"Missing verdict for {meta.id}"
        assert isinstance(result.ok, bool), f"Missing ok flag for {meta.id}"
        print(f"  ✅ run {meta.id} -> {result.verdict} ({result.duration_ms}ms)")
    print("✅ run_t0_commands")


def test_receipt_paths():
    """Receipt root must be creatable."""
    adapter = RCCAdapter()
    # Run a command with receipt to create the tree
    adapter.run("roxy.status", receipt=True)
    rec = adapter.read_latest_receipt("roxy.status")
    # May be None on first run, but should not crash
    print(f"✅ receipt_paths (latest: {rec.run_id if rec else 'none'})")


def test_no_raw_shell_for_commands():
    """Adapter must use RCC CLI, not raw shell."""
    adapter = RCCAdapter()
    # Verify the adapter delegates to rcc.mjs
    assert "rcc.mjs" in str(adapter.rcc_cli)
    print("✅ no_raw_shell_for_commands")


def main():
    print("=" * 60)
    print("RCC GTK4 Adapter Smoke Test")
    print("=" * 60)

    tests = [
        test_adapter_status,
        test_list_commands,
        test_dry_run_all,
        test_run_t0_commands,
        test_receipt_paths,
        test_no_raw_shell_for_commands,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1

    print("=" * 60)
    if failed == 0:
        print("RCC_GTK4_ADAPTER_SMOKE_PASS")
        return 0
    else:
        print(f"RCC_GTK4_ADAPTER_SMOKE_FAIL ({failed}/{len(tests)})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
