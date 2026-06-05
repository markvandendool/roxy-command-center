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
        self._refresh()
        return True

    def _refresh(self):
        # Clear
        while self._content.get_first_child():
            self._content.remove(self._content.get_first_child())

        # Pending Judge jobs
        judge_jobs = get_judge_service().get_pending_jobs()
        if judge_jobs:
            self._content.append(self._make_section_header(f"⚖️ Judge Jobs ({len(judge_jobs)} pending)"))
            for job in judge_jobs[:5]:
                self._content.append(self._make_job_row(job))

        # Pending action receipts
        receipts = list_receipts(limit=20)
        pending = [r for r in receipts if r.get("status") in ("queued", "pending")]
        if pending:
            self._content.append(self._make_section_header(f"📋 Pending Actions ({len(pending)})"))
            for r in pending[:5]:
                self._content.append(self._make_receipt_row(r))

        # Recent Kimi assignments
        assignments = list_assignments(limit=5)
        if assignments:
            self._content.append(self._make_section_header(f"🤖 Kimi Assignments ({len(assignments)} recent)"))
            for a in assignments[:5]:
                self._content.append(self._make_assignment_row(a))

        # Recent investigations
        investigations = list_investigations(limit=5)
        if investigations:
            self._content.append(self._make_section_header(f"🔍 Investigations ({len(investigations)} recent)"))
            for inv in investigations[:5]:
                self._content.append(self._make_investigation_row(inv))

        # Recent completed/failed
        completed = [r for r in receipts if r.get("status") in ("completed", "failed")]
        if completed:
            self._content.append(self._make_section_header(f"✅ Recent Outcomes ({len(completed)})"))
            for r in completed[:5]:
                self._content.append(self._make_receipt_row(r))

        # Blocked
        blocked = [r for r in receipts if r.get("status") == "blocked"]
        if blocked:
            self._content.append(self._make_section_header(f"🚧 Blocked ({len(blocked)})"))
            for r in blocked[:5]:
                self._content.append(self._make_receipt_row(r))

        # Empty state
        if not any([judge_jobs, pending, assignments, investigations, completed, blocked]):
            empty = Gtk.Label(label="No actions yet. Use mission cards to create actions.")
            empty.add_css_class("dim-label")
            empty.set_margin_top(24)
            self._content.append(empty)

        self._count_label.set_label(f"{len(receipts)} total")

    def _make_section_header(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("moc-row-title")
        lbl.set_xalign(0)
        lbl.set_margin_top(8)
        return lbl

    def _make_job_row(self, job: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("moc-object-row")
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        status = job.get("status", "?")
        icon = "⏳" if status == "queued" else "🔄" if status == "running" else "✅" if status == "completed" else "❌"

        icon_lbl = Gtk.Label(label=icon)
        row.append(icon_lbl)

        text = f"{job.get('jobId', '?')}: {job.get('context', '?')[:40]}"
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("moc-row-subtitle")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(lbl)

        return row

    def _make_receipt_row(self, receipt: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("moc-object-row")
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        status = receipt.get("status", "?")
        action = receipt.get("action", "?")
        icon = {
            "queued": "⏳", "pending": "🔄", "completed": "✅",
            "failed": "❌", "blocked": "🚧",
        }.get(status, "❓")

        icon_lbl = Gtk.Label(label=icon)
        row.append(icon_lbl)

        text = f"{action}: {receipt.get('missionTitle', '?')[:40]}"
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("moc-row-subtitle")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(lbl)

        return row

    def _make_assignment_row(self, assignment: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("moc-object-row")
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        status = assignment.get("status", "?")
        icon = "⏳" if status == "queued" else "✅" if status == "completed" else "❌"

        icon_lbl = Gtk.Label(label=icon)
        row.append(icon_lbl)

        text = f"kimi → {assignment.get('targetSurface', '?')}: {assignment.get('missionTitle', '?')[:30]}"
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("moc-row-subtitle")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(lbl)

        return row

    def _make_investigation_row(self, inv: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("moc-object-row")
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        status = inv.get("status", "?")
        icon = "⏳" if status == "queued" else "✅" if status == "completed" else "❌"

        icon_lbl = Gtk.Label(label=icon)
        row.append(icon_lbl)

        text = f"investigate: {inv.get('missionTitle', '?')[:30]}"
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("moc-row-subtitle")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(lbl)

        return row
