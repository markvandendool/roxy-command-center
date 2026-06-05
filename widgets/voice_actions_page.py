#!/usr/bin/env python3
"""
Voice / Actions Page — Action pipeline visibility.
Recent receipts, squads, pending confirmations.
Reads from output/regent/action-receipts.ndjson.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any, List
import json
from pathlib import Path
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.voice_status_provider import get_voice_status


class VoiceActionsPage(Gtk.ScrolledWindow):
    """Action pipeline and voice command visibility."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._rows_box: Optional[Gtk.Box] = None
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        title = Gtk.Label(label="Voice / Actions")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        # Voice Foundry Status Card
        self._build_voice_status_card(main_box)

        # Stats
        self.stats_label = Gtk.Label(label="")
        self.stats_label.add_css_class("caption")
        self.stats_label.set_xalign(0)
        main_box.append(self.stats_label)

        # Receipts section
        receipts_title = Gtk.Label(label="Recent Receipts")
        receipts_title.add_css_class("title-3")
        receipts_title.set_xalign(0)
        receipts_title.set_margin_top(8)
        main_box.append(receipts_title)

        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_box.append(self.rows_box)

    def _build_voice_status_card(self, parent):
        """Build the Voice Foundry status card."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.add_css_class("card")
        parent.append(card)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card.append(header)

        self._voice_status_label = Gtk.Label(label="Voice Foundry: checking...")
        self._voice_status_label.add_css_class("title-3")
        self._voice_status_label.set_xalign(0)
        self._voice_status_label.set_hexpand(True)
        header.append(self._voice_status_label)

        self._voice_detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._voice_detail_box.set_margin_start(8)
        card.append(self._voice_detail_box)

        self._update_voice_status()

    def _update_voice_status(self):
        """Update Voice Foundry status display."""
        try:
            status = get_voice_status()
            classification = status.get("classification", "UNKNOWN")

            color_class = {
                "READY": "status-healthy",
                "DORMANT": "status-warn",
                "MISSING_SERVICE": "status-blocked",
                "PATH_ISSUE": "status-blocked",
                "BLOCKED": "status-blocked",
            }.get(classification, "status-warn")

            self._voice_status_label.set_label(f"Voice Foundry: {classification}")
            self._voice_status_label.add_css_class(color_class)

            # Clear details
            while self._voice_detail_box.get_first_child():
                self._voice_detail_box.remove(self._voice_detail_box.get_first_child())

            # Service details
            for svc_name, svc_info in status.get("services", {}).items():
                alive = "🟢" if svc_info.get("alive") else "🔴"
                port = svc_info.get("port", "?")
                lbl = Gtk.Label(label=f"{alive} {svc_name} (:{port})")
                lbl.add_css_class("moc-row-subtitle")
                lbl.set_xalign(0)
                self._voice_detail_box.append(lbl)

            # Blocker / recommendation
            if status.get("blocker"):
                blocker_lbl = Gtk.Label(label=f"⚠️ {status['blocker']}")
                blocker_lbl.add_css_class("caption")
                blocker_lbl.add_css_class("status-blocked-text")
                blocker_lbl.set_xalign(0)
                self._voice_detail_box.append(blocker_lbl)

            if status.get("recommendation"):
                rec_lbl = Gtk.Label(label=f"💡 {status['recommendation']}")
                rec_lbl.add_css_class("caption")
                rec_lbl.set_xalign(0)
                self._voice_detail_box.append(rec_lbl)

        except Exception as exc:
            self._voice_status_label.set_label(f"Voice Foundry: ERROR ({exc})")

    def _read_receipts(self) -> List[dict]:
        try:
            path = Path.home() / ".roxy" / ".." / ".." / "mnt" / "work" / "ssot" / "mindsong-juke-hub" / "output" / "regent" / "action-receipts.ndjson"
            # Try relative from home
            alt_path = Path("/mnt/work/ssot/mindsong-juke-hub/output/regent/action-receipts.ndjson")
            target = alt_path if alt_path.exists() else path
            if not target.exists():
                return []
            lines = target.read_text().strip().splitlines()
            receipts = []
            for line in lines[-20:]:
                try:
                    receipts.append(json.loads(line))
                except Exception:
                    pass
            return list(reversed(receipts))
        except Exception:
            return []

    def update(self, data: dict):
        self._update_voice_status()
        receipts = self._read_receipts()

        # Stats
        total = len(receipts)
        failed = sum(1 for r in receipts if r.get("exit", 0) != 0)
        self.stats_label.set_label(f"Last 20 receipts · {total} total · {failed} failed")

        # Clear rows
        while self.rows_box.get_first_child():
            self.rows_box.remove(self.rows_box.get_first_child())

        for receipt in receipts:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_top(2)
            row.set_margin_bottom(2)

            verb = receipt.get("verb", "?")
            exit_code = receipt.get("exit", 0)
            ts = receipt.get("ts", "")[:19]
            detail = receipt.get("detail", "")[:60]

            status_icon = "❌" if exit_code != 0 else "✓"
            text = f"{status_icon} {ts} · {verb} · {detail}"

            lbl = Gtk.Label(label=text)
            lbl.add_css_class("monospace-small")
            lbl.set_xalign(0)
            lbl.set_hexpand(True)
            if exit_code != 0:
                lbl.add_css_class("status-blocked-text")
            row.append(lbl)
            self.rows_box.append(row)
