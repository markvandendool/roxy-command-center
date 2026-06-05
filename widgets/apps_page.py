#!/usr/bin/env python3
"""
Apps / Processes Page — Top CPU and RAM offenders.
No direct ps. Reads from performance.topCpuOffenders / topRamOffenders.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any, List


class ProcessTable(Gtk.Box):
    """A simple table of process data."""

    def __init__(self, title: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)

        # Title
        t = Gtk.Label(label=title)
        t.add_css_class("title-3")
        t.set_xalign(0)
        self.append(t)

        # Column header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_start(8)
        header.set_margin_end(8)
        header.add_css_class("process-header")
        for col, width in [("PID", 80), ("CPU%", 70), ("RSS MiB", 90), ("Command", -1)]:
            lbl = Gtk.Label(label=col)
            lbl.add_css_class("monospace")
            lbl.set_xalign(0)
            if width > 0:
                lbl.set_size_request(width, -1)
            else:
                lbl.set_hexpand(True)
            header.append(lbl)
        self.append(header)

        # Rows container
        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.append(self.rows_box)

    def set_rows(self, processes: List[dict]):
        # Clear existing
        while self.rows_box.get_first_child():
            self.rows_box.remove(self.rows_box.get_first_child())

        for proc in processes[:15]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(2)
            row.set_margin_bottom(2)
            row.add_css_class("process-row")

            pid = str(proc.get("pid", "?"))
            pcpu = proc.get("pcpu", 0)
            # host-vitals.mjs outputs rssGb; convert to MiB for display
            rss_gb = proc.get("rssGb", 0)
            rss_mib = proc.get("rssMiB", 0)
            if rss_mib == 0 and rss_gb > 0:
                rss_mib = rss_gb * 1024
            comm = proc.get("comm", "?")
            args = proc.get("args", "")[:60]

            # Suspicious badge
            is_suspicious = pcpu > 50 or rss_mib > 1000
            if is_suspicious:
                row.add_css_class("process-suspicious")

            cols = [
                (pid, 80),
                (f"{pcpu:.1f}" if pcpu else "—", 70),
                (f"{rss_mib:.0f}", 90),
                (f"{comm} {args}" if args else comm, -1),
            ]
            for text, width in cols:
                lbl = Gtk.Label(label=text)
                lbl.add_css_class("monospace-small")
                lbl.set_xalign(0)
                if width > 0:
                    lbl.set_size_request(width, -1)
                else:
                    lbl.set_hexpand(True)
                row.append(lbl)

            self.rows_box.append(row)


class AppsPage(Gtk.ScrolledWindow):
    """Process offender tables."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        title = Gtk.Label(label="Apps & Processes")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        self.cpu_table = ProcessTable("Top CPU Offenders")
        main_box.append(self.cpu_table)

        self.ram_table = ProcessTable("Top RAM Offenders")
        main_box.append(self.ram_table)

    def update(self, data: dict):
        perf = data.get("performance") or {}

        cpu_off = perf.get("topCpuOffenders", [])
        if isinstance(cpu_off, dict):
            cpu_off = cpu_off.get("offenders", [])
        self.cpu_table.set_rows(cpu_off)

        ram_off = perf.get("topRamOffenders") or data.get("hostMemory", {}).get("topRamOffenders", [])
        if isinstance(ram_off, dict):
            ram_off = ram_off.get("offenders", [])
        self.ram_table.set_rows(ram_off)
