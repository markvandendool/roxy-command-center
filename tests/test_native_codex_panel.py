#!/usr/bin/env python3
"""Native Codex panel formatting and GTK construction coverage."""

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

sys.path.insert(0, str(Path(__file__).parent.parent))

from widgets.rcc_command_page import RCCCommandPage, format_codex_status


def sample_response():
    return {
        "ok": True,
        "result": {
            "schemaVersion": "mindsong-codex-integration-status.v1",
            "status": "CODEX_INTEGRATION_DEGRADED",
            "cli": {"version": "0.144.1"},
            "identity": {"id": "codex-regent", "exactSurfaceBound": True, "matchCount": 1},
            "mcp": {"inSync": True},
            "capture": {"status": "CAPTURE_UPGRADE_PLAN_NEEDS_BINDING"},
            "blockers": [{"code": "CODEX_CAPTURE_GRADE_BINDING_INCOMPLETE"}],
        },
        "receipt": {
            "receiptId": "receipt-123",
            "source": {"shellVersion": "abc123"},
            "policy": {"tier": "T0"},
        },
    }


def test_formatter_preserves_required_truth():
    status = format_codex_status(sample_response())
    assert status["schemaVersion"] == "mindsong-codex-integration-status.v1"
    assert status["cliVersion"] == "0.144.1"
    assert status["identity"] == "codex-regent"
    assert status["identityBound"]
    assert status["mcpInSync"]
    assert status["sourceCommit"] == "abc123"
    assert status["receiptId"] == "receipt-123"
    assert status["blockers"] == ["CODEX_CAPTURE_GRADE_BINDING_INCOMPLETE"]


def test_gateway_error_stays_visible():
    status = format_codex_status({"ok": False, "error": "gateway unavailable"})
    assert not status["ok"]
    assert status["status"] == "CODEX_STATUS_UNAVAILABLE"
    assert status["error"] == "gateway unavailable"


def test_native_panel_constructs_and_renders():
    page = RCCCommandPage()
    page._show_codex_status(sample_response())
    assert page.codex_summary.get_label() == "CODEX_INTEGRATION_DEGRADED"
    details = page.codex_details.get_label()
    assert "codex-regent" in details
    assert "receipt-123" in details
    assert "abc123" in details


def main() -> int:
    Gtk.init()
    test_formatter_preserves_required_truth()
    test_gateway_error_stays_visible()
    test_native_panel_constructs_and_renders()
    print("RCC_NATIVE_CODEX_PANEL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
