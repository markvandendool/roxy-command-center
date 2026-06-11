#!/usr/bin/env python3
"""
RCC Command Page — Canonical command surface for the GTK4 Command Center.

This page consumes the SSOT RCC Command Kernel. It does NOT implement
command logic. It delegates every action to services/rcc_adapter.py.

Features:
- List all RCC commands with tier/world badges
- Dry-run any command
- Run T0 commands directly
- Show latest receipt per command
- Link to full receipt path
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango
from typing import Optional, Dict, Any
from pathlib import Path
import json

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from services.rcc_adapter import RCCAdapter, RCCCommandMeta, RCCRunResult


# ── Tier Badge Styles ───────────────────────────────────────────────

TIER_CSS = {
    "T0": "tier-t0",   # Read — safe
    "T1": "tier-t1",   # Safe write
    "T2": "tier-t2",   # Gated
    "T3": "tier-t3",   # Dangerous
}

TIER_LABEL = {
    "T0": "📖",
    "T1": "✏️",
    "T2": "🔒",
    "T3": "☠️",
}

WORLD_CSS = {
    "stage": "world-stage",
    "moon": "world-moon",
    "backlot": "world-backlot",
    "broadcast-shared": "world-shared",
}

PINNED_COMMANDS = [
    "factory.status",
    "factory.models",
    "factory.walkers",
    "factory.hardware",
    "factory.routes",
    "roxy.models",
    "agent.agents",
]


# ── Command Row ─────────────────────────────────────────────────────

class RCCCommandRow(Gtk.Box):
    """A single row representing one RCC command."""

    def __init__(self, meta: RCCCommandMeta, adapter: RCCAdapter, on_run: callable):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.meta = meta
        self.adapter = adapter
        self._on_run = on_run

        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row_box.set_hexpand(True)
        self.append(row_box)

        # Left: command info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_hexpand(True)

        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Command ID
        id_label = Gtk.Label(label=meta.id)
        id_label.add_css_class("monospace")
        id_label.set_xalign(0)
        name_box.append(id_label)

        # Tier badge
        tier_badge = Gtk.Label(label=f"{TIER_LABEL.get(meta.risk_tier, '?')} {meta.risk_tier}")
        tier_badge.add_css_class(TIER_CSS.get(meta.risk_tier, "tier-t0"))
        name_box.append(tier_badge)

        # World badge
        world_badge = Gtk.Label(label=meta.world)
        world_badge.add_css_class(WORLD_CSS.get(meta.world, "world-moon"))
        name_box.append(world_badge)

        info_box.append(name_box)

        # Description
        desc = Gtk.Label(label=meta.label)
        desc.set_xalign(0)
        desc.add_css_class("caption")
        info_box.append(desc)

        # Receipt link (initially hidden)
        self.receipt_link = Gtk.Button(label="🧾 receipt")
        self.receipt_link.set_visible(False)
        self.receipt_link.connect("clicked", self._on_receipt_clicked)
        info_box.append(self.receipt_link)

        row_box.append(info_box)

        # Right: action buttons
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.dry_btn = Gtk.Button(label="Dry-run")
        self.dry_btn.set_tooltip_text(f"Plan {meta.id} without executing")
        self.dry_btn.connect("clicked", self._on_dry_run)
        actions.append(self.dry_btn)

        self.run_btn = Gtk.Button(label="Run")
        self.run_btn.set_tooltip_text(f"Execute {meta.id}")
        self.run_btn.connect("clicked", self._on_run_clicked)
        # T2/T3 require confirmation; disable run by default for them
        if meta.risk_tier in ("T2", "T3"):
            self.run_btn.set_sensitive(False)
            self.run_btn.set_tooltip_text(f"{meta.risk_tier} command requires confirmation")
        actions.append(self.run_btn)

        row_box.append(actions)

        # Result area (initially hidden)
        self.result_area = Gtk.TextView()
        self.result_area.set_editable(False)
        self.result_area.set_monospace(True)
        self.result_area.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.result_area.set_visible(False)
        self.result_area.set_margin_top(8)
        self.result_area.set_size_request(-1, 120)
        self.append(self.result_area)

    def _on_dry_run(self, btn):
        self._execute(dry_run=True)

    def _on_run_clicked(self, btn):
        self._execute(dry_run=False)

    def _execute(self, dry_run: bool):
        self._on_run(self.meta.id, dry_run)

    def show_result(self, result: RCCRunResult):
        """Display a run result in this row."""
        text = f"Verdict: {result.verdict}\n"
        text += f"Duration: {result.duration_ms}ms\n"
        if result.warnings:
            text += f"Warnings: {', '.join(result.warnings)}\n"
        if result.errors:
            text += f"Errors: {', '.join(result.errors)}\n"
        if result.next_action:
            text += f"Next: {result.next_action}\n"
        if result.data:
            text += f"\nData:\n{json.dumps(result.data, indent=2, default=str)}\n"

        buffer = self.result_area.get_buffer()
        buffer.set_text(text)
        self.result_area.set_visible(True)

        if result.receipt_path:
            self.receipt_link.set_visible(True)
            self._receipt_path = result.receipt_path

    def _on_receipt_clicked(self, btn):
        if hasattr(self, "_receipt_path") and self._receipt_path:
            # Open receipt in default app or copy path
            print(f"[RCC] Receipt: {self._receipt_path}")


# ── RCC Command Page ────────────────────────────────────────────────

class RCCCommandPage(Gtk.ScrolledWindow):
    """
    Main RCC command surface for the GTK4 Command Center.

    Consumes the SSOT RCC Command Kernel. All commands are delegated.
    """

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.adapter = RCCAdapter()
        self._rows: Dict[str, RCCCommandRow] = {}
        self._build_ui()
        self._load_commands()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_box.append(header)

        title = Gtk.Label(label="RCC Command Kernel")
        title.add_css_class("title-1")
        title.set_xalign(0)
        title.set_hexpand(True)
        header.append(title)

        # Adapter status
        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("caption")
        header.append(self.status_label)

        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.set_tooltip_text("Refresh command list")
        refresh.connect("clicked", lambda *_: self._load_commands())
        header.append(refresh)

        # Legend
        legend = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        legend.set_margin_bottom(8)
        for tier, icon in TIER_LABEL.items():
            l = Gtk.Label(label=f"{icon} {tier}")
            l.add_css_class("caption")
            legend.append(l)
        main_box.append(legend)

        # DARK FACTORY quick strip
        factory_title = Gtk.Label(label="DARK FACTORY")
        factory_title.add_css_class("title-3")
        factory_title.set_xalign(0)
        main_box.append(factory_title)

        factory_subtitle = Gtk.Label(label="Readiness, Qwen MTP, 6900XT, Judge, walking agents, and hardware missions from the SSOT RCC kernel.")
        factory_subtitle.add_css_class("caption")
        factory_subtitle.set_xalign(0)
        factory_subtitle.set_wrap(True)
        main_box.append(factory_subtitle)

        quick_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        quick_box.set_margin_bottom(8)
        self.quick_box = quick_box
        main_box.append(quick_box)

        self.factory_status = Gtk.Label(label="Factory status: not checked")
        self.factory_status.add_css_class("caption")
        self.factory_status.set_xalign(0)
        main_box.append(self.factory_status)

        # Commands list
        self.commands_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_box.append(self.commands_box)

        # Results container (for expandable result views)
        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.append(self.results_box)

        # Separator
        main_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Receipts section
        receipts_title = Gtk.Label(label="Latest Receipts")
        receipts_title.add_css_class("title-3")
        receipts_title.set_xalign(0)
        receipts_title.set_margin_top(16)
        main_box.append(receipts_title)

        self.receipts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_box.append(self.receipts_box)

    def _load_commands(self):
        """Load and display all RCC commands."""
        # Clear existing
        while self.commands_box.get_first_child():
            self.commands_box.remove(self.commands_box.get_first_child())
        while self.results_box.get_first_child():
            self.results_box.remove(self.results_box.get_first_child())

        # Check adapter health
        status = self.adapter.status()
        if not status["rcc_cli_exists"]:
            self.status_label.set_text("❌ RCC CLI not found")
            err = Gtk.Label(label="RCC CLI not found. Is the SSOT repo mounted?")
            err.add_css_class("error")
            self.commands_box.append(err)
            return

        self.status_label.set_text("✅ RCC connected")

        commands = self.adapter.list_commands()
        if not commands:
            empty = Gtk.Label(label="No RCC commands found. Run rcc --list to verify.")
            empty.add_css_class("dim-label")
            self.commands_box.append(empty)
            return

        self._build_quick_commands(commands)

        for meta in commands:
            row = RCCCommandRow(meta, self.adapter, self._on_command_run)
            self.commands_box.append(row)
            self._rows[meta.id] = row

        # Also load receipts
        self._load_receipts()
        self._refresh_factory_status()

    def _build_quick_commands(self, commands: list[RCCCommandMeta]):
        """Build pinned DARK FACTORY command buttons."""
        while self.quick_box.get_first_child():
            self.quick_box.remove(self.quick_box.get_first_child())

        by_id = {c.id: c for c in commands}
        for command_id in PINNED_COMMANDS:
            if command_id not in by_id:
                continue
            btn = Gtk.Button(label=command_id)
            btn.set_tooltip_text(by_id[command_id].label)
            btn.connect("clicked", lambda _btn, cid=command_id: self._on_command_run(cid, False))
            self.quick_box.append(btn)

    def _refresh_factory_status(self):
        """Run factory.status in the background and summarize readiness."""
        import threading

        def worker():
            result = self.adapter.run("factory.status", receipt=True)
            GLib.idle_add(self._show_factory_status, result)

        threading.Thread(target=worker, daemon=True).start()

    def _show_factory_status(self, result: RCCRunResult):
        ready = {}
        if isinstance(result.data, dict):
            ready = result.data.get("ready", {}) or {}
        ready_text = " ".join(f"{k}={'OK' if v else 'NO'}" for k, v in ready.items())
        suffix = f" | {ready_text}" if ready_text else ""
        self.factory_status.set_text(f"Factory status: {result.verdict}{suffix}")
        return False

    def _on_command_run(self, command_id: str, dry_run: bool):
        """Handle a command run request from a row."""
        row = self._rows.get(command_id)
        if not row:
            # Quick commands can fire before row lookup if the list is refreshing.
            self.factory_status.set_text(f"Running {command_id}...")

        # Run in a thread to avoid blocking UI
        import threading
        def worker():
            result = self.adapter.run(command_id, dry_run=dry_run, receipt=True)
            GLib.idle_add(self._show_result, command_id, result)

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, command_id: str, result: RCCRunResult):
        """Show result in the UI (called on main thread)."""
        row = self._rows.get(command_id)
        if row:
            row.show_result(result)
        elif command_id.startswith("factory."):
            self._show_factory_status(result)

        # Refresh receipts
        self._load_receipts()
        return False  # GLib.idle_add callback

    def _load_receipts(self):
        """Load and display latest RCC receipts."""
        while self.receipts_box.get_first_child():
            self.receipts_box.remove(self.receipts_box.get_first_child())

        receipts = self.adapter.list_receipts(limit=10)
        if not receipts:
            empty = Gtk.Label(label="No receipts yet.")
            empty.add_css_class("dim-label")
            self.receipts_box.append(empty)
            return

        for rec in receipts:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(4)
            box.set_margin_bottom(4)

            verdict_icon = "✅" if rec.verdict == "PASS" else "⚠️" if rec.verdict == "DEGRADED" else "❌"
            label = Gtk.Label(label=f"{verdict_icon} {rec.command_id} — {rec.verdict} ({rec.duration_ms}ms)")
            label.set_xalign(0)
            label.set_hexpand(True)
            box.append(label)

            if rec.path:
                btn = Gtk.Button.new_from_icon_name("document-open-symbolic")
                btn.set_tooltip_text(str(rec.path))
                btn.connect("clicked", lambda _b, p=rec.path: print(f"[RCC] Open receipt: {p}"))
                box.append(btn)

            self.receipts_box.append(box)
