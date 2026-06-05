#!/usr/bin/env python3
"""
Performance Page — Situational awareness, not device enumeration.

Groups:
  SYSTEM   → CPU, Memory, Swap, Thermals
  COMPUTE  → GPUs by real name (RTX 4000 Ada, RX 6900 XT, W5700X)
  STORAGE  → Root, Work, NVMe
  NETWORK  → Network throughput
  AGENTS   → Agents, MCP

Principles:
  - Names over indices
  - Semantic groups over kernel enumeration
  - Current value + history + threshold (Grafana principle)
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any, List

from widgets.circular_meter import CircularMeter
from widgets.graph_widget import SparklineWidget
from services.telemetry_collector import get_collector


class DeviceCard(Gtk.Box):
    """A compact device card with value, subtitle, and sparkline."""

    def __init__(self, title: str, icon_name: str = "", color: tuple = (0.0, 0.8, 0.5)):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("device-card")
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(header)

        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(18)
            header.append(icon)

        self.title_label = Gtk.Label(label=title)
        self.title_label.add_css_class("device-title")
        self.title_label.set_xalign(0)
        self.title_label.set_hexpand(True)
        header.append(self.title_label)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        body.set_hexpand(True)
        self.append(body)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text_box.set_hexpand(True)
        body.append(text_box)

        self.value_label = Gtk.Label(label="--")
        self.value_label.add_css_class("device-value")
        self.value_label.set_xalign(0)
        text_box.append(self.value_label)

        self.subtitle_label = Gtk.Label(label="")
        self.subtitle_label.add_css_class("device-subtitle")
        self.subtitle_label.set_xalign(0)
        self.subtitle_label.set_wrap(True)
        text_box.append(self.subtitle_label)

        self.meter = CircularMeter(size=72)
        self.meter.set_valign(Gtk.Align.CENTER)
        self.meter.set_visible(False)
        body.append(self.meter)

        # Sparkline
        self.sparkline = SparklineWidget(color=color)
        self.sparkline.set_margin_top(4)
        self.append(self.sparkline)

        self._color = color

    def set_title(self, title: str):
        self.title_label.set_label(title)

    def set_value(self, value: str, subtitle: str = "", meter_percent: Optional[float] = None, meter_caption: str = "", status: str = "info", history: list = None):
        self.value_label.set_label(value)
        self.subtitle_label.set_label(subtitle)
        if meter_percent is None:
            self.meter.set_visible(False)
            self.sparkline.set_visible(True)
            if history is not None and len(history) >= 2:
                self.sparkline.set_history(history)
            else:
                self.sparkline.set_history([])
        else:
            self.meter.set_visible(True)
            self.sparkline.set_visible(False)
            self.meter.set_value(meter_percent, f"{meter_percent:.0f}%", meter_caption, status)

    def set_status_color(self, status: str):
        """status: healthy, warn, blocked"""
        self.remove_css_class("status-healthy")
        self.remove_css_class("status-warn")
        self.remove_css_class("status-blocked")
        if status in ("healthy", "warn", "blocked"):
            self.add_css_class(f"status-{status}")


class SectionBox(Gtk.Box):
    """A titled section containing a FlowBox of cards."""

    def __init__(self, title: str, max_columns: int = 4):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)

        self.title_label = Gtk.Label(label=title)
        self.title_label.add_css_class("title-3")
        self.title_label.set_xalign(0)
        self.append(self.title_label)

        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_homogeneous(True)
        self.flow.set_min_children_per_line(1)
        self.flow.set_max_children_per_line(max_columns)
        self.flow.set_column_spacing(12)
        self.flow.set_row_spacing(12)
        self.append(self.flow)

    def add_card(self, widget: Gtk.Widget):
        self.flow.append(widget)

    def clear_cards(self):
        while True:
            child = self.flow.get_first_child()
            if child is None:
                break
            self.flow.remove(child)


class PerformancePage(Gtk.ScrolledWindow):
    """
    Performance dashboard organized by situational awareness:
    SYSTEM → COMPUTE → STORAGE → NETWORK → AGENTS
    """

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._cards: Dict[str, DeviceCard] = {}
        self._gpu_cards: Dict[int, DeviceCard] = {}
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        # Title
        title = Gtk.Label(label="Performance")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        # Status strip
        self.status_strip = Gtk.Label(label="Loading...")
        self.status_strip.add_css_class("caption")
        self.status_strip.set_xalign(0)
        main_box.append(self.status_strip)

        # ── SYSTEM ──
        self.system_section = SectionBox("System", max_columns=4)
        main_box.append(self.system_section)

        for key, title, icon, color in [
            ("cpu", "CPU", "computer-symbolic", (0.13, 0.77, 0.37)),
            ("memory", "Memory", "drive-harddisk-symbolic", (0.48, 0.23, 0.93)),
            ("swap", "Swap", "media-removable-symbolic", (0.96, 0.62, 0.04)),
            ("thermals", "Thermals", "temperature-symbolic", (0.93, 0.27, 0.27)),
        ]:
            card = DeviceCard(title, icon, color)
            self._cards[key] = card
            self.system_section.add_card(card)

        # ── COMPUTE ──
        self.compute_section = SectionBox("Compute", max_columns=3)
        main_box.append(self.compute_section)
        # GPU cards created dynamically on first data arrival

        # ── STORAGE ──
        self.storage_section = SectionBox("Storage", max_columns=4)
        main_box.append(self.storage_section)

        for key, title, icon, color in [
            ("root", "Root", "drive-harddisk-system-symbolic", (0.20, 0.80, 0.60)),
            ("work", "Work", "folder-symbolic", (0.13, 0.59, 0.95)),
            ("nvme", "NVMe", "drive-harddisk-symbolic", (0.58, 0.30, 0.95)),
        ]:
            card = DeviceCard(title, icon, color)
            self._cards[key] = card
            self.storage_section.add_card(card)

        # ── NETWORK ──
        self.network_section = SectionBox("Network", max_columns=3)
        main_box.append(self.network_section)

        for key, title, icon, color in [
            ("network", "Network", "network-wireless-symbolic", (0.13, 0.77, 0.37)),
        ]:
            card = DeviceCard(title, icon, color)
            self._cards[key] = card
            self.network_section.add_card(card)

        # ── AGENTS ──
        self.agents_section = SectionBox("Agents", max_columns=3)
        main_box.append(self.agents_section)

        for key, title, icon, color in [
            ("agents", "Agents", "applications-games-symbolic", (0.96, 0.62, 0.04)),
            ("mcp", "MCP", "preferences-system-symbolic", (0.48, 0.23, 0.93)),
        ]:
            card = DeviceCard(title, icon, color)
            self._cards[key] = card
            self.agents_section.add_card(card)

        # ── Detail sections ──
        detail_title = Gtk.Label(label="CPU Detail")
        detail_title.add_css_class("title-3")
        detail_title.set_xalign(0)
        detail_title.set_margin_top(16)
        main_box.append(detail_title)

        self.cpu_detail = Gtk.Label(label="")
        self.cpu_detail.add_css_class("monospace")
        self.cpu_detail.set_xalign(0)
        main_box.append(self.cpu_detail)

        gpu_title = Gtk.Label(label="GPU Detail")
        gpu_title.add_css_class("title-3")
        gpu_title.set_xalign(0)
        gpu_title.set_margin_top(16)
        main_box.append(gpu_title)

        self.gpu_detail = Gtk.Label(label="")
        self.gpu_detail.add_css_class("monospace")
        self.gpu_detail.set_xalign(0)
        main_box.append(self.gpu_detail)

    def _ensure_gpu_card(self, index: int, name: str, color: tuple) -> DeviceCard:
        """Lazy-create GPU cards with real hardware names."""
        if index in self._gpu_cards:
            card = self._gpu_cards[index]
            card.set_title(name)
            return card

        # Create new card
        card = DeviceCard(name, "video-display-symbolic", color)
        self._gpu_cards[index] = card
        self.compute_section.add_card(card)
        return card

    def update(self, data: dict):
        perf = data.get("performance") or {}
        if not perf:
            return

        perf_status = perf.get("status", "unknown")
        self.status_strip.set_label(f"Status: {perf_status.upper()}")
        if perf_status == "blocked":
            self.status_strip.add_css_class("status-blocked-text")
        elif perf_status == "warn":
            self.status_strip.add_css_class("status-warn-text")
        else:
            self.status_strip.remove_css_class("status-blocked-text")
            self.status_strip.remove_css_class("status-warn-text")

        coll = get_collector()

        # ── SYSTEM ──
        # CPU
        cpu = perf.get("cpu", {})
        cpu_util = cpu.get("utilPct", 0)
        load1 = cpu.get("load1", 0)
        if "cpu" in self._cards:
            c = self._cards["cpu"]
            status = "blocked" if cpu_util > 80 else "warn" if cpu_util > 60 else "healthy"
            c.set_value(f"{cpu_util:.1f}%", f"Load: {load1:.1f}", cpu_util, "CPU", status)
            c.set_status_color(status)

        # Memory
        mem = data.get("hostMemory", {}).get("ram", {})
        used_gb = mem.get("usedGb", 0)
        total_gb = mem.get("totalGb", 1)
        pct = (used_gb / total_gb * 100) if total_gb > 0 else 0
        if "memory" in self._cards:
            c = self._cards["memory"]
            status = "blocked" if pct > 90 else "warn" if pct > 75 else "healthy"
            c.set_value(f"{used_gb:.1f} GB", f"{pct:.0f}% of {total_gb:.0f} GB", pct, "RAM", status)
            c.set_status_color(status)

        # Swap
        swap = data.get("hostMemory", {}).get("swap", {})
        swap_used = swap.get("usedGb", 0)
        swap_total = swap.get("totalGb", 1)
        swap_pct = (swap_used / swap_total * 100) if swap_total > 0 else 0
        if "swap" in self._cards:
            c = self._cards["swap"]
            status = "blocked" if swap_pct > 80 else "warn" if swap_pct > 50 else "healthy"
            c.set_value(f"{swap_used:.1f} GB", f"{swap_pct:.0f}% of {swap_total:.0f} GB", swap_pct, "swap", status)
            c.set_status_color(status)

        # Thermals
        temps = data.get("idle_health", {}).get("temperature", {})
        hottest = temps.get("hottest_c", 0)
        cpu_temp = temps.get("cpu_c", 0)
        gpu_temp = temps.get("gpu_max_c", 0)
        nvme_temp = temps.get("nvme_max_c", 0)
        if "thermals" in self._cards:
            c = self._cards["thermals"]
            status = "blocked" if hottest > 85 else "warn" if hottest > 70 else "healthy"
            subtitle = f"CPU {cpu_temp:.0f}°C  GPU {gpu_temp:.0f}°C  NVMe {nvme_temp:.0f}°C"
            c.set_value(f"{hottest:.0f}°C", subtitle, history=coll.get("thermals"))
            c.set_status_color(status)

        # ── COMPUTE (GPUs by real name) ──
        gpu_data = perf.get("gpu", {})
        gpus = gpu_data.get("gpus", [])
        gpu_colors = [
            (0.13, 0.59, 0.95),  # NVIDIA blue
            (0.93, 0.27, 0.27),  # AMD red
            (0.58, 0.30, 0.95),  # AMD pro purple
        ]
        for i, gpu in enumerate(gpus[:3]):
            name = gpu.get("name", f"GPU {i}")
            # Shorten common names
            name = self._shorten_gpu_name(name)
            util = gpu.get("utilPct", 0)
            temp = gpu.get("tempC", 0)
            vram_used = gpu.get("vramUsedMiB", 0)
            vram_total = gpu.get("vramTotalMiB", 1)
            vram_pct = (vram_used / vram_total * 100) if vram_total > 0 else 0
            status = "blocked" if util > 95 else "warn" if util > 80 else "healthy"

            # Map collector key: gpu0, gpu1, gpu2
            card = self._ensure_gpu_card(i, name, gpu_colors[i % len(gpu_colors)])
            subtitle = f"{temp}°C · {vram_used / 1024:.1f} / {vram_total / 1024:.1f} GB"
            card.set_value(f"{util:.0f}%", subtitle, util, "GPU", status)
            card.set_status_color(status)

        # Hide GPU cards that no longer have data
        for idx in list(self._gpu_cards.keys()):
            if idx >= len(gpus):
                self._gpu_cards[idx].set_visible(False)

        # ── STORAGE ──
        # Root
        root = data.get("storage", {}).get("root", {})
        if "root" in self._cards and root:
            c = self._cards["root"]
            used = root.get("used_gb", 0)
            total = root.get("total_gb", 1)
            pct = root.get("used_pct", (used / total * 100) if total > 0 else 0)
            status = "blocked" if pct > 90 else "warn" if pct > 75 else "healthy"
            c.set_value(f"{pct:.0f}%", f"{used:.0f} / {total:.0f} GB", pct, "Root", status)
            c.set_status_color(status)

        # Work
        work = data.get("storage", {}).get("work", {})
        if "work" in self._cards and work:
            c = self._cards["work"]
            used = work.get("used_gb", 0)
            total = work.get("total_gb", 1)
            pct = work.get("used_pct", (used / total * 100) if total > 0 else 0)
            status = "blocked" if pct > 90 else "warn" if pct > 75 else "healthy"
            c.set_value(f"{pct:.0f}%", f"{used:.0f} / {total:.0f} GB", pct, "Work", status)
            c.set_status_color(status)

        # NVMe
        nvme = perf.get("nvme", {})
        devices = nvme.get("devices", [])
        total_ops = sum(
            (d.get("readOps", d.get("reads", 0)) or 0) +
            (d.get("writeOps", d.get("writes", 0)) or 0)
            for d in devices
        )
        if "nvme" in self._cards:
            c = self._cards["nvme"]
            c.set_value(f"{total_ops:,}", f"ops · {len(devices)} devices", history=coll.get("nvme"))
            c.set_status_color("healthy")

        # ── NETWORK ──
        net = perf.get("network", {})
        interfaces = net.get("interfaces", [])
        total_mb = sum(
            (d.get("rxMiB", 0) or (d.get("rxBytes", 0) or 0) / (1024 * 1024)) +
            (d.get("txMiB", 0) or (d.get("txBytes", 0) or 0) / (1024 * 1024))
            for d in interfaces
        )
        if "network" in self._cards:
            c = self._cards["network"]
            c.set_value(f"{total_mb:.0f} MB", f"{len(interfaces)} interfaces", history=coll.get("network"))
            c.set_status_color("healthy")

        # ── AGENTS ──
        agents = perf.get("agents", {})
        total = agents.get("total", 0)
        abandoned = agents.get("abandoned", 0)
        if "agents" in self._cards:
            c = self._cards["agents"]
            c.set_value(str(total), f"{abandoned} abandoned" if abandoned else "All healthy", history=coll.get("agents"))
            c.set_status_color("blocked" if abandoned > 5 else "warn" if abandoned > 0 else "healthy")

        mcp = perf.get("mcp", {})
        mcp_total = mcp.get("total", 0)
        if "mcp" in self._cards:
            c = self._cards["mcp"]
            c.set_value(str(mcp_total), "MCP processes", history=coll.get("mcp"))
            c.set_status_color("blocked" if mcp_total > 80 else "warn" if mcp_total > 50 else "healthy")

        # ── Detail text ──
        load5 = cpu.get("load5", 0)
        load15 = cpu.get("load15", 0)
        self.cpu_detail.set_label(f"util: {cpu_util:.1f}%  load1: {load1:.1f}  load5: {load5:.1f}  load15: {load15:.1f}")

        gpu_lines = []
        for i, gpu in enumerate(gpus):
            name = gpu.get("name", f"GPU {i}")
            util = gpu.get("utilPct", 0)
            temp = gpu.get("tempC", 0)
            vram = gpu.get("vramUsedMiB", 0)
            vram_total = gpu.get("vramTotalMiB", 0)
            gpu_lines.append(f"{name}: {util}% · {temp}°C · VRAM {vram}/{vram_total} MiB")
        self.gpu_detail.set_label("\n".join(gpu_lines) if gpu_lines else "No GPU data")

    @staticmethod
    def _shorten_gpu_name(name: str) -> str:
        """Convert verbose GPU names to readable labels."""
        if not name:
            return "GPU"
        # NVIDIA
        if "RTX 4000 Ada Generation" in name:
            return "RTX 4000 Ada"
        if "RTX A4000" in name:
            return "RTX A4000"
        # AMD
        if "RX 6900 XT" in name:
            return "RX 6900 XT"
        if "W5700X" in name:
            return "W5700X"
        if "Radeon Pro" in name:
            # Extract model after "Radeon Pro"
            parts = name.split("Radeon Pro ")
            if len(parts) > 1:
                return f"Radeon Pro {parts[1].split()[0]}"
        # Fallback: first 20 chars
        return name if len(name) <= 24 else name[:21] + "..."
