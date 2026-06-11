#!/usr/bin/env python3
"""
Operator Safety Rail — Mission Center-style mini telemetry for RCC Chat.

Shows live CPU, Memory, GPU, and route health in a compact vertical strip.
Each row: name | value | subtitle | sparkline | status dot.

Data source: daemon performance dict (same schema as PerformancePage).
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from typing import Optional, Dict, Any, List, Tuple

from widgets.graph_widget import SparklineWidget
from services.telemetry_collector import get_collector


def _status_color(status: str) -> Tuple[float, float, float]:
    """Return RGB color for a status string."""
    if status == "ready":
        return (0.21, 0.82, 0.50)  # moc_green
    if status == "warn":
        return (0.96, 0.71, 0.29)  # moc_amber
    if status == "error":
        return (0.94, 0.39, 0.39)  # moc_red
    return (0.56, 0.63, 0.71)  # moc_ink_2 grey


class MetricRow(Gtk.Box):
    """Single compact metric row: name value subtitle sparkline status."""

    def __init__(self, name: str, color: Tuple[float, float, float] = (0.31, 0.76, 0.97)):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_css_class("safety-metric-row")
        self.set_margin_top(1)
        self.set_margin_bottom(1)

        self._name = name
        self._color = color

        # Name label
        self.name_label = Gtk.Label(label=name)
        self.name_label.add_css_class("safety-metric-name")
        self.name_label.set_xalign(0)
        self.name_label.set_width_chars(8)
        self.append(self.name_label)

        # Value label
        self.value_label = Gtk.Label(label="--")
        self.value_label.add_css_class("safety-metric-value")
        self.value_label.set_xalign(1)
        self.value_label.set_width_chars(6)
        self.append(self.value_label)

        # Subtitle label
        self.subtitle_label = Gtk.Label(label="")
        self.subtitle_label.add_css_class("safety-metric-subtitle")
        self.subtitle_label.set_xalign(0)
        self.subtitle_label.set_hexpand(True)
        self.subtitle_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        self.append(self.subtitle_label)

        # Sparkline
        self.sparkline = SparklineWidget(color=color)
        self.sparkline.set_size_request(48, 18)
        self.sparkline.add_css_class("safety-sparkline")
        self.append(self.sparkline)

        # Status dot (colored circle using a small Label with Unicode)
        self.status_dot = Gtk.Label(label="●")
        self.status_dot.set_markup("<span color='#8fa0b5'>●</span>")
        self.append(self.status_dot)

    def set_value(self, value: str, subtitle: str = "", status: str = "off", history: Optional[List[float]] = None):
        self.value_label.set_label(value)
        self.subtitle_label.set_label(subtitle)

        # Status dot color
        rgb = _status_color(status)
        hex_color = "#{:02x}{:02x}{:02x}".format(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
        self.status_dot.set_markup(f'<span color="{hex_color}">●</span>')

        # Sparkline
        if history is not None and len(history) >= 2:
            self.sparkline.set_history(history)
            self.sparkline.set_visible(True)
        else:
            self.sparkline.set_visible(False)


class OperatorSafetyRail(Gtk.Box):
    """
    Compact vertical telemetry rail for the Chat cockpit.

    Sections:
      System  → CPU, Memory
      Compute → RTX 4000 Ada, W5700X, RX 6900 XT
      Routes  → Chat Proxy, LiteLLM, Ada Frontier, 6900XT Coder, Judge, Ollama
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("safety-rail")
        self.set_size_request(260, -1)

        self._rows: Dict[str, MetricRow] = {}
        self._gpu_rows: Dict[int, MetricRow] = {}
        self._build_ui()

    def _build_ui(self):
        # Title
        title = Gtk.Label(label="Live System")
        title.add_css_class("safety-rail-title")
        title.set_xalign(0)
        title.set_margin_bottom(4)
        self.append(title)

        # ── System ──
        self._add_section_header("System")
        self._add_row("cpu", "CPU", (0.31, 0.76, 0.97))
        self._add_row("memory", "MEM", (0.48, 0.23, 0.93))

        # ── Compute ──
        self._add_section_header("Compute")
        self._add_row("gpu_ada", "Ada", (0.13, 0.59, 0.95))
        self._add_row("gpu_w5700x", "W5700X", (0.93, 0.27, 0.27))
        self._add_row("gpu_6900xt", "6900XT", (0.58, 0.30, 0.95))

        # ── Routes ──
        self._add_section_header("Routes")
        self._add_row("proxy", "Proxy", (0.21, 0.82, 0.50))
        self._add_row("litellm", "LiteLLM", (0.21, 0.82, 0.50))
        self._add_row("route_ada", "Ada Frontier", (0.13, 0.59, 0.95))
        self._add_row("route_6900xt", "6900XT Coder", (0.58, 0.30, 0.95))
        self._add_row("route_judge", "Judge", (0.56, 0.63, 0.71))
        self._add_row("route_ollama", "Ollama", (0.56, 0.63, 0.71))

    def _add_section_header(self, text: str):
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("caption")
        lbl.set_xalign(0)
        lbl.set_margin_top(6)
        lbl.set_margin_bottom(2)
        lbl.set_opacity(0.6)
        self.append(lbl)

    def _add_row(self, key: str, name: str, color: Tuple[float, float, float]):
        row = MetricRow(name, color)
        self._rows[key] = row
        self.append(row)

    def update(self, data: dict):
        """Update rail from daemon performance dict."""
        perf = data.get("performance") or {}
        coll = get_collector()

        # ── System ──
        cpu = perf.get("cpu", {})
        cpu_util = cpu.get("utilPct", 0)
        load1 = cpu.get("load1", 0)
        if "cpu" in self._rows:
            status = "error" if cpu_util > 80 else "warn" if cpu_util > 60 else "ready"
            self._rows["cpu"].set_value(
                f"{cpu_util:.0f}%",
                f"load {load1:.1f}",
                status,
                coll.get("cpu")
            )

        mem = data.get("hostMemory", {}).get("ram", {})
        used_gb = mem.get("usedGb", 0)
        total_gb = mem.get("totalGb", 1)
        pct = (used_gb / total_gb * 100) if total_gb > 0 else 0
        if "memory" in self._rows:
            status = "error" if pct > 90 else "warn" if pct > 75 else "ready"
            self._rows["memory"].set_value(
                f"{used_gb:.0f}G",
                f"{pct:.0f}% of {total_gb:.0f}G",
                status,
                coll.get("memory")
            )

        # ── Compute (GPUs) ──
        gpu_data = perf.get("gpu", {})
        gpus = gpu_data.get("gpus", [])

        # Map GPUs by name pattern
        for i, gpu in enumerate(gpus):
            name = gpu.get("name", "")
            util = gpu.get("utilPct", 0)
            temp = gpu.get("tempC", 0)
            vram_used = gpu.get("vramUsedMiB", 0)
            vram_total = gpu.get("vramTotalMiB", 1)
            vram_gb = vram_used / 1024
            vram_total_gb = vram_total / 1024

            subtitle = f"{temp}°C · {vram_gb:.1f}/{vram_total_gb:.0f}G"
            status = "error" if util > 95 else "warn" if util > 80 else "ready"

            if "RTX 4000" in name or "RTX A4000" in name:
                self._rows["gpu_ada"].set_value(f"{util:.0f}%", subtitle, status, coll.get(f"gpu{i}"))
            elif "RX 6900 XT" in name:
                self._rows["gpu_6900xt"].set_value(f"{util:.0f}%", subtitle, status, coll.get(f"gpu{i}"))
            elif "W5700X" in name or "Radeon Pro" in name:
                self._rows["gpu_w5700x"].set_value(f"{util:.0f}%", subtitle, status, coll.get(f"gpu{i}"))

        # ── Routes (from data or default to grey) ──
        # Chat Proxy
        proxy_ok = data.get("roxy_chat_proxy", {}).get("ok", False)
        self._rows["proxy"].set_value(
            "OK" if proxy_ok else "?",
            ":4001",
            "ready" if proxy_ok else "off"
        )

        # LiteLLM
        litellm_ok = data.get("litellm", {}).get("ok", False)
        self._rows["litellm"].set_value(
            "OK" if litellm_ok else "?",
            ":4000",
            "ready" if litellm_ok else "off"
        )

        # Active route info
        active_model = data.get("active_model", "")
        if active_model:
            if "frontier" in active_model.lower():
                self._rows["route_ada"].set_value("ACTIVE", "", "ready")
            elif "6900xt-coder" in active_model.lower():
                self._rows["route_6900xt"].set_value("ACTIVE", "", "ready")

        # Judge (:8084) — check if backend listening
        judge_ok = data.get("judge_backend", {}).get("ok", False)
        self._rows["route_judge"].set_value(
            "OK" if judge_ok else "OFF",
            ":8084",
            "ready" if judge_ok else "off"
        )

        # Ollama (:11434)
        ollama_ok = data.get("ollama", {}).get("ok", False)
        self._rows["route_ollama"].set_value(
            "OK" if ollama_ok else "OFF",
            ":11434",
            "ready" if ollama_ok else "off"
        )
