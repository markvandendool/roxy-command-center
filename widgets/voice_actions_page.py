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
