#!/usr/bin/env python3
"""Focused GTK coverage for asynchronous RCC command catalog loading."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.rcc_adapter import RCCCommandMeta
import widgets.rcc_command_page as command_page


COMMANDS = [
    RCCCommandMeta(
        id="roxy.status",
        label="Roxy machine state",
        namespace="roxy",
        world="moon",
        risk_tier="T0",
    )
]


class RecordingAdapter:
    def __init__(self, *, error: Exception | None = None, commands=None):
        self.error = error
        self.commands = COMMANDS if commands is None else commands
        self.list_thread_id = None
        self.finished = threading.Event()

    def status(self):
        return {"rcc_cli_exists": True}

    def list_commands(self):
        self.list_thread_id = threading.get_ident()
        try:
            if self.error:
                raise self.error
            return self.commands
        finally:
            self.finished.set()


def wait_for_state(page, expected: str, timeout: float = 2.0):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if page.command_catalog_state == expected:
            return
        time.sleep(0.01)
    raise AssertionError(
        f"catalog state remained {page.command_catalog_state!r}; expected {expected!r}"
    )


def build_page(adapter: RecordingAdapter):
    with patch.object(command_page, "RCCAdapter", return_value=adapter):
        page = command_page.RCCCommandPage()
    page._load_receipts = lambda: None
    page._refresh_factory_status = lambda: None
    page._refresh_route_doctor = lambda: None
    return page


def test_catalog_subprocess_path_runs_outside_gtk_thread():
    gtk_thread_id = threading.get_ident()
    adapter = RecordingAdapter()
    page = build_page(adapter)

    assert page.command_catalog_state == "loading"
    assert page.command_catalog_message.get_label() == "Loading RCC command catalog..."
    assert not page.command_refresh_button.get_sensitive()
    assert adapter.finished.wait(1), "catalog worker did not finish"
    assert adapter.list_thread_id != gtk_thread_id

    wait_for_state(page, "ready")
    assert page.command_refresh_button.get_sensitive()
    assert page.status_label.get_label() == "RCC connected: 1 commands"
    assert "roxy.status" in page._rows


def test_catalog_worker_error_is_visible_and_retryable():
    adapter = RecordingAdapter(error=TimeoutError("RCC timed out after 30s"))
    page = build_page(adapter)

    assert adapter.finished.wait(1), "catalog error worker did not finish"
    wait_for_state(page, "error")

    message = page.command_catalog_message.get_label()
    assert "RCC command catalog unavailable" in message
    assert "timed out after 30s" in message
    assert page.command_refresh_button.get_sensitive()


def test_adapter_timeout_collapsed_to_empty_is_still_visible_as_error():
    adapter = RecordingAdapter(commands=[])
    page = build_page(adapter)

    assert adapter.finished.wait(1), "empty catalog worker did not finish"
    wait_for_state(page, "error")

    message = page.command_catalog_message.get_label()
    assert "returned no commands" in message
    assert "timed out" in message


def test_stale_catalog_result_cannot_replace_newer_refresh():
    adapter = RecordingAdapter()
    page = build_page(adapter)
    assert adapter.finished.wait(1)
    wait_for_state(page, "ready")

    current_generation = page._command_load_generation
    page._show_command_catalog(current_generation - 1, [], "stale failure")

    assert page.command_catalog_state == "ready"
    assert "roxy.status" in page._rows


def main() -> int:
    Gtk.init()
    test_catalog_subprocess_path_runs_outside_gtk_thread()
    test_catalog_worker_error_is_visible_and_retryable()
    test_adapter_timeout_collapsed_to_empty_is_still_visible_as_error()
    test_stale_catalog_result_cannot_replace_newer_refresh()
    print("RCC_COMMAND_CATALOG_ASYNC_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
