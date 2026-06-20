#!/usr/bin/env python3
"""
Orchestrator Panel — Minimal actionable overview.

Shows pending actions, queued jobs, recent outcomes.
No new backend — reads receipt files only.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango
from typing import Optional, List
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.action_receipt_service import list_receipts, get_recent_by_action
from services.judge_service import get_judge_service
from services.kimi_assignment_service import list_assignments
from services.investigation_service import list_investigations


class OrchestratorPanel(Gtk.Box):
    """Minimal orchestrator overview panel."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("orchestrator-panel")
        self.set_margin_top(12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_bottom(12)

        self._build_ui()
        self._refresh()
        # Auto-refresh every 10s
        GLib.timeout_add_seconds(10, self._on_auto_refresh)

    def _build_ui(self):
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(header)

        title = Gtk.Label(label="Orchestrator")
        title.add_css_class("moc-section-label")
        title.set_hexpand(True)
        title.set_xalign(0)
        header.append(title)

        self._count_label = Gtk.Label(label="—")
        self._count_label.add_css_class("moc-row-subtitle")
        header.append(self._count_label)

        # Filter bar
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        filter_box.set_margin_top(4)
        filter_box.set_margin_bottom(4)
        self.append(filter_box)

        self._filter_buttons: dict = {}
        filters = [
            ("all", "All"),
            ("pending", "Pending"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("judge", "Judge"),
            ("kimi", "Kimi"),
            ("investigate", "Investigate"),
        ]
        for key, label in filters:
            btn = Gtk.ToggleButton(label=label)
            btn.add_css_class("pill")
            btn.add_css_class("caption")
            if key == "all":
                btn.set_active(True)
            btn.connect("toggled", self._on_filter_changed, key)
            filter_box.append(btn)
            self._filter_buttons[key] = btn

        self._current_filter = "all"

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(4)
        sep.set_margin_bottom(4)
        self.append(sep)

        # Scrollable content
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroll.set_child(self._content)

    def _on_auto_refresh(self):
        if not self.get_mapped():
            return True
        self._refresh()
        return True

    def _on_filter_changed(self, button, filter_key):
        if button.get_active():
            self._current_filter = filter_key
            # Deactivate other buttons
            for key, btn in self._filter_buttons.items():
                if key != filter_key:
                    btn.set_active(False)
            self._refresh()
        else:
            # Ensure at least one filter is active
            if not any(btn.get_active() for btn in self._filter_buttons.values()):
                self._filter_buttons["all"].set_active(True)

    def _matches_filter(self, item: dict) -> bool:
        """Check if an item matches the current filter."""
        f = self._current_filter
        if f == "all":
            return True
        status = item.get("status", "").lower()
        action = item.get("action", "").lower()
        if f == "pending":
            return status in ("queued", "pending", "running")
        if f == "completed":
            return status == "completed"
        if f == "failed":
            return status in ("failed", "blocked", "timeout")
        if f == "judge":
            return action == "judge"
        if f == "kimi":
            return action == "kimi_assign"
        if f == "investigate":
            return action == "investigate"
        return True

    def _refresh(self):
        # Clear
        while self._content.get_first_child():
            self._content.remove(self._content.get_first_child())

        # Collect all items into unified list with type tags
        all_items = []

        # Judge jobs (as receipts)
        for job in get_judge_service().list_jobs(limit=20):
            all_items.append({
                "type": "judge",
                "action": "judge",
                "status": job.get("status", "?"),
                "title": job.get("context", "Judge Review"),
                "id": job.get("jobId", "?"),
                "data": job,
            })

        # Action receipts
        for r in list_receipts(limit=30):
            all_items.append({
                "type": "receipt",
                "action": r.get("action", "?"),
                "status": r.get("status", "?"),
                "title": r.get("missionTitle", "?"),
                "id": r.get("receiptPath", "?").split("/")[-1],
                "data": r,
            })

        # Kimi assignments
        for a in list_assignments(limit=10):
            all_items.append({
                "type": "kimi",
                "action": "kimi_assign",
                "status": a.get("status", "?"),
                "title": a.get("missionTitle", "?"),
                "id": a.get("packetId", "?"),
                "data": a,
            })

        # Investigations
        for inv in list_investigations(limit=10):
            all_items.append({
                "type": "investigate",
                "action": "investigate",
                "status": inv.get("status", "?"),
                "title": inv.get("missionTitle", "?"),
                "id": inv.get("packetId", "?"),
                "data": inv,
            })

        # Apply filter
        filtered = [item for item in all_items if self._matches_filter(item)]

        # Group by status for display
        pending_items = [i for i in filtered if i["status"] in ("queued", "pending", "running")]
        completed_items = [i for i in filtered if i["status"] == "completed"]
        failed_items = [i for i in filtered if i["status"] in ("failed", "blocked", "timeout")]

        # Show sections
        if pending_items:
            self._content.append(self._make_section_header(f"⏳ Pending ({len(pending_items)})"))
            for item in pending_items[:8]:
                self._content.append(self._make_item_row(item))

        if completed_items:
            self._content.append(self._make_section_header(f"✅ Completed ({len(completed_items)})"))
            for item in completed_items[:8]:
                self._content.append(self._make_item_row(item))

        if failed_items:
            self._content.append(self._make_section_header(f"❌ Failed ({len(failed_items)})"))
            for item in failed_items[:8]:
                self._content.append(self._make_item_row(item))

        # Empty state
        if not filtered:
            empty = Gtk.Label(label="No actions match the current filter.")
            empty.add_css_class("dim-label")
            empty.set_margin_top(24)
            self._content.append(empty)

        self._count_label.set_label(f"{len(filtered)} shown / {len(all_items)} total")

    def _make_section_header(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("moc-row-title")
        lbl.set_xalign(0)
        lbl.set_margin_top(8)
        return lbl

    def _make_item_row(self, item: dict) -> Gtk.Box:
        """Unified row for any action item — clickable for details."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("moc-object-row")
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        status = item.get("status", "?")
        action = item.get("action", "?")
        icon_map = {
            "queued": "⏳", "pending": "🔄", "running": "🔄",
            "completed": "✅", "failed": "❌", "blocked": "🚧", "timeout": "⏰",
        }
        icon = icon_map.get(status, "❓")

        icon_lbl = Gtk.Label(label=icon)
        row.append(icon_lbl)

        type_icon = {"judge": "⚖️", "kimi_assign": "🤖", "investigate": "🔍"}.get(action, "📋")
        text = f"{type_icon} {item.get('title', '?')[:40]}"
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("moc-row-subtitle")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(lbl)

        # Click to show details
        gesture = Gtk.GestureClick()
        gesture.connect("released", self._on_item_clicked, item)
        row.add_controller(gesture)
        row.set_tooltip_text(f"Click for details: {item.get('id', '?')}")

        return row

    def _on_item_clicked(self, gesture, n_press, x, y, item):
        """Show detail dialog for an action item."""
        data = item.get("data", {})
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"{item.get('action', '?').upper()}: {item.get('title', '?')[:50]}",
        )

        # Build detail text
        details = []
        details.append(f"Status: {item.get('status', '?')}")
        details.append(f"ID: {item.get('id', '?')}")

        if item["type"] == "judge":
            details.append(f"Result: {data.get('result', '')[:200]}")
            if data.get('error'):
                details.append(f"Error: {data.get('error')}")
        elif item["type"] == "receipt":
            details.append(f"Target: {data.get('targetAgent', '?')} / {data.get('targetLane', '?')}")
            details.append(f"Authority: {data.get('authority', '?')}")
            if data.get('error'):
                details.append(f"Error: {data.get('error')}")
        elif item["type"] == "kimi":
            details.append(f"Target: {data.get('targetSurface', '?')}")
            details.append(f"Agent: {data.get('targetAgent', '?')}")
        elif item["type"] == "investigate":
            details.append(f"Question: {data.get('question', '?')[:100]}")
            details.append(f"Safe mode: {data.get('safeMode', '?')}")

        dialog.set_secondary_text("\n".join(details))
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()
