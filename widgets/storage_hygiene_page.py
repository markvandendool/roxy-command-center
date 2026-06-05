#!/usr/bin/env python3
"""
Storage / Hygiene Page — compact storage instruments and debris risk.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Dict
from pathlib import Path
import shutil

from widgets.circular_meter import CircularMeter


class StorageMeter(Gtk.Box):
    """Circular storage meter with a compact detail line."""

    def __init__(self, title: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("moc-card")
        self.add_css_class("storage-meter-card")
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)

        self.title_label = Gtk.Label(label=title)
        self.title_label.add_css_class("overview-title")
        self.title_label.set_xalign(0)
        self.append(self.title_label)

        self.meter = CircularMeter(size=118)
        self.meter.set_halign(Gtk.Align.CENTER)
        self.append(self.meter)

        self.detail_label = Gtk.Label(label="")
        self.detail_label.add_css_class("overview-subtitle")
        self.detail_label.set_xalign(0)
        self.detail_label.set_wrap(True)
        self.append(self.detail_label)

    def set(self, used_gb: float, total_gb: float, detail: str = ""):
        pct = (used_gb / total_gb * 100) if total_gb > 0 else 0
        status = "blocked" if pct > 90 else "warn" if pct > 70 else "healthy"
        self.meter.set_value(pct, f"{pct:.0f}%", "used", status)
        self.detail_label.set_label(f"{used_gb:.1f} / {total_gb:.1f} GB · {detail}")

        self.remove_css_class("status-healthy")
        self.remove_css_class("status-warn")
        self.remove_css_class("status-blocked")
        self.add_css_class(f"status-{status}")


class StorageHygienePage(Gtk.ScrolledWindow):
    """Storage bomb prevention dashboard."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._meters: Dict[str, StorageMeter] = {}
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.add_css_class("moc-surface")
        self.set_child(main_box)

        title = Gtk.Label(label="Storage & Hygiene")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        instrument_title = Gtk.Label(label="Capacity Instruments")
        instrument_title.add_css_class("moc-section-label")
        instrument_title.set_xalign(0)
        main_box.append(instrument_title)

        self.meter_grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        self.meter_grid.set_column_homogeneous(True)
        main_box.append(self.meter_grid)

        for col, (key, label) in enumerate([
            ("root", "Root"),
            ("work", "Work"),
            ("tmpfs", "Tmpfs"),
            ("swap", "Swap"),
        ]):
            meter = StorageMeter(label)
            meter.set_hexpand(True)
            self._meters[key] = meter
            self.meter_grid.attach(meter, col, 0, 1, 1)

        facts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        facts.set_homogeneous(True)
        main_box.append(facts)

        debris_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        debris_card.add_css_class("moc-panel")
        facts.append(debris_card)

        debris_title = Gtk.Label(label="Build Debris")
        debris_title.add_css_class("moc-section-label")
        debris_title.set_xalign(0)
        debris_card.append(debris_title)

        self.debris_label = Gtk.Label(label="")
        self.debris_label.add_css_class("monospace")
        self.debris_label.set_xalign(0)
        self.debris_label.set_wrap(True)
        debris_card.append(self.debris_label)

        backup_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        backup_card.add_css_class("moc-panel")
        facts.append(backup_card)

        backup_title = Gtk.Label(label="Backup")
        backup_title.add_css_class("moc-section-label")
        backup_title.set_xalign(0)
        backup_card.append(backup_title)

        self.backup_label = Gtk.Label(label="Backup status not yet connected.")
        self.backup_label.add_css_class("overview-subtitle")
        self.backup_label.set_xalign(0)
        self.backup_label.set_wrap(True)
        backup_card.append(self.backup_label)

    def _count_t8k_dirs(self) -> tuple:
        try:
            tmp = Path("/tmp")
            dirs = [d for d in tmp.iterdir() if d.is_dir() and d.name.startswith("t8k-prod-dist-")]
            total_size_gb = sum(
                sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                for d in dirs
            ) / (1024 ** 3)
            return len(dirs), total_size_gb
        except Exception:
            return 0, 0.0

    def _usage_for_path(self, path: str) -> tuple[float, float]:
        try:
            usage = shutil.disk_usage(path)
            return usage.used / (1024 ** 3), usage.total / (1024 ** 3)
        except Exception:
            return 0.0, 0.0

    def update(self, data: dict):
        host_mem = data.get("hostMemory", {})
        ram = host_mem.get("ram", {})
        swap = host_mem.get("swap", {})
        storage = data.get("storage", {})

        def _get_num(obj, *keys):
            for k in keys:
                if k in obj:
                    v = obj[k]
                    if isinstance(v, (int, float)):
                        return v
            return 0

        root = storage.get("root", {})
        if "root" in self._meters:
            self._meters["root"].set(
                _get_num(root, "used_gb", "usedGb"),
                _get_num(root, "total_gb", "totalGb") or 1,
                root.get("mount", "/")
            )

        work = storage.get("work", {})
        if "work" in self._meters:
            self._meters["work"].set(
                _get_num(work, "used_gb", "usedGb"),
                _get_num(work, "total_gb", "totalGb") or 1,
                work.get("mount", "/mnt/work")
            )

        t8k_count, t8k_size = self._count_t8k_dirs()
        ram_total = _get_num(ram, "totalGb", "total_gb")
        ram_used = _get_num(ram, "usedGb", "used_gb")
        tmp_used, tmp_total = self._usage_for_path("/tmp")
        if "tmpfs" in self._meters:
            self._meters["tmpfs"].set(
                tmp_used,
                tmp_total if tmp_total > 0 else 1,
                f"{t8k_count} t8k dirs · debris {t8k_size:.1f} GB · RAM {ram_used:.1f}/{ram_total:.1f} GB"
            )

        swap_used = _get_num(swap, "usedGb", "used_gb")
        swap_total = _get_num(swap, "totalGb", "total_gb", "swapTotalGb")
        if swap_total <= 0:
            swap_total = 32
        if "swap" in self._meters:
            self._meters["swap"].set(swap_used, swap_total, "system swap")

        self.debris_label.set_label(f"/tmp/t8k-prod-dist-*\n{t8k_count} dirs · {t8k_size:.1f} GB total")
