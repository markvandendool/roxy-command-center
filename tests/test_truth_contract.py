#!/usr/bin/env python3
"""
Truth Contract Tests — Enforce operator-trustworthy cockpit invariants.

Run:
    python3 tests/test_truth_contract.py

Stories covered:
- Story 1: Green-state gate (provenance required for PASS rendering)
- Story 6: factory.routes hard gate (four required OpenCode routes)
- Story 9: Progression row model placeholders (receipt + state fields)
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from widgets.truth_badge import TruthBadge
from services.rcc_adapter import RCCAdapter


REQUIRED_ROUTE_IDS = {
    "frontier-opencode-lite",
    "decode-6900xt-opencode-lite",
    "judge-direct",
    "judge-opencode",
}


def test_truth_badge_pass_requires_provenance():
    """PASS without source/command/timestamp/receiptPath must render DEGRADED."""
    badge = TruthBadge("Test")
    badge.set_truth("PASS", provenance={
        "source": "test",
        "command": "test.cmd",
        "timestamp": "2026-01-01T00:00:00Z",
        "receiptPath": "/tmp/receipt.json",
    })
    assert badge.state == "PASS", f"Expected PASS, got {badge.state}"

    badge2 = TruthBadge("Test")
    badge2.set_truth("PASS", provenance={
        "source": "test",
        "command": "test.cmd",
        # missing timestamp and receiptPath
    })
    assert badge2.state == "DEGRADED", f"Expected DEGRADED for missing provenance, got {badge2.state}"

    badge3 = TruthBadge("Test")
    badge3.set_truth("PASS", provenance=None)
    assert badge3.state == "DEGRADED", f"Expected DEGRADED for None provenance, got {badge3.state}"
    print("✅ truth_badge_pass_requires_provenance")


def test_factory_routes_hard_gate():
    """factory.routes must expose the four canonical OpenCode routes."""
    adapter = RCCAdapter()
    result = adapter.run("factory.routes", receipt=False, json_output=True)
    assert result.ok, f"factory.routes failed: {result.errors}"

    data = result.data or {}
    routes = data.get("routes") or []
    found_ids = {r.get("id") for r in routes if isinstance(r, dict)}

    missing = REQUIRED_ROUTE_IDS - found_ids
    assert not missing, f"factory.routes missing required routes: {sorted(missing)}"

    # Each required route must have status or ok field
    routes_by_id = {r.get("id"): r for r in routes if isinstance(r, dict)}
    for rid in REQUIRED_ROUTE_IDS:
        route = routes_by_id[rid]
        has_status = "status" in route
        has_ok = "ok" in route
        assert has_status or has_ok, f"Route {rid} missing status/ok field"

    print(f"✅ factory_routes_hard_gate ({len(found_ids)} routes, all required present)")


def test_receipt_path_is_recorded():
    """factory.routes with --receipt must record receiptPath."""
    adapter = RCCAdapter()
    result = adapter.run("factory.routes", receipt=True, json_output=True)
    assert result.ok, f"factory.routes --receipt failed: {result.errors}"
    assert result.receipt_path, f"factory.routes --receipt missing receipt_path"
    assert Path(result.receipt_path).exists(), f"Receipt file missing: {result.receipt_path}"
    print(f"✅ receipt_path_is_recorded ({result.receipt_path})")


if __name__ == "__main__":
    test_truth_badge_pass_requires_provenance()
    test_factory_routes_hard_gate()
    test_receipt_path_is_recorded()
    print("\nTRUTH_CONTRACT_PASS")
