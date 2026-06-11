#!/usr/bin/env python3
"""
Performance Page — Mission Center-style situational awareness.

Layout (Mission Center inspired):
  LEFT  → Device list (CPU, Memory, GPUs, Storage, Network)
  CENTER → Big graph for selected device
  RIGHT  → Exact current values and facts

Selection:
  - Click a device in the left list to focus it
  - Big graph shows 10-minute history
  - Facts panel shows exact current values

Principles:
  - Names over indices
  - Semantic groups
  - Current value + history + threshold
  - Left rail always visible
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gdk
from typing import Optional, Dict, Any, List, Tuple

from widgets.circular_meter import CircularMeter
from widgets.graph_widget import GraphWidget, GraphConfig, GraphStyle
from services.telemetry_collector import get_collector


class DeviceListItem(Gtk.Box):
    """A selectable row in the left device rail."""

    def __init__(self, device_id: str, name: str, icon_name: str = "",
                 color: Tuple[float, float, float] = (0.13, 0.77, 0.37)):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.device_id = device_id
        self._color = color
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_margin_start(8)
        self.set_margin_end(8)

        # Selection styling
        self.add_css_class("device-list-item")

        # Icon
        if icon_name:
            self._icon = Gtk.Image.new_from_icon_name(icon_name)
            self._icon.set_pixel_size(16)
            self.append(self._icon)
        else:
            self._icon = None

        # Name
        self._name_label = Gtk.Label(label=name)
        self._name_label.add_css_class("caption")
        self._name_label.set_xalign(0)
        self._name_label.set_hexpand(True)
        self.append(self._name_label)

        # Value
        self._value_label = Gtk.Label(label="--")
        self._value_label.add_css_class("caption")
        self._value_label.add_css_class("monospace")
        self._value_label.set_xalign(1)
        self.append(self._value_label)

        # Status dot
        self._dot = Gtk.Label(label="●")
        self._dot.set_markup("<span color='#8fa0b5'>●</span>")
        self.append(self._dot)

    def set_value(self, value: str, status: str = "healthy"):
        self._value_label.set_label(value)
        if status == "healthy":
            color = "#35d07f"
        elif status == "warn":
            color = "#f5b64a"
        elif status == "blocked":
            color = "#f06464"
        else:
            color = "#8fa0b5"
        self._dot.set_markup(f'<span color="{color}">●</span>')


class DeviceDetailView(Gtk.Box):
    """Main panel: big graph + facts for the selected device."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        # Title
        self._title = Gtk.Label(label="Select a device")
        self._title.add_css_class("title-2")
        self._title.set_xalign(0)
        self.append(self._title)

        # Big graph
        config = GraphConfig(
            history_seconds=600,
            update_interval_ms=5000,
            style=GraphStyle.FILLED,
            color=(0.31, 0.76, 0.97),
            fill_alpha=0.25,
            line_width=2.0,
            show_grid=True,
            grid_lines=5,
            show_current_value=True,
            value_format="{:.1f}",
            value_suffix="",
        )
        self._graph = GraphWidget(config)
        self._graph.set_vexpand(True)
        self._graph.set_size_request(-1, 300)
        self.append(self._graph)

        # Facts grid
        self._facts_box = Gtk.Grid()
        self._facts_box.set_row_spacing(8)
        self._facts_box.set_column_spacing(16)
        self._facts_box.set_margin_top(8)
        self.append(self._facts_box)

        self._fact_labels: Dict[str, Gtk.Label] = {}
        self._current_device: Optional[str] = None

    def show_device(self, device_id: str, name: str, history: List[float],
                    facts: Dict[str, str], color: Tuple[float, float, float] = (0.31, 0.76, 0.97)):
        """Display a device in the detail view."""
        self._current_device = device_id
        self._title.set_label(name)

        # Update graph color
        self._graph._line_color = color
        self._graph._fill_color = (*color, self._graph.config.fill_alpha)

        # Load history into graph
        self._graph._data.clear()
        for v in history:
            self._graph._data.append(float(v))
        # Pad to max points
        while len(self._graph._data) < self._graph._max_points:
            self._graph._data.append(0.0)
        self._graph.queue_draw()

        # Update facts
        # Clear old facts
        while True:
            child = self._facts_box.get_first_child()
            if child is None:
                break
            self._facts_box.remove(child)
        self._fact_labels.clear()

        row = 0
        col = 0
        for key, value in facts.items():
            key_lbl = Gtk.Label(label=key)
            key_lbl.add_css_class("caption")
            key_lbl.set_opacity(0.7)
            key_lbl.set_xalign(0)
            self._facts_box.attach(key_lbl, col * 2, row, 1, 1)

            val_lbl = Gtk.Label(label=value)
            val_lbl.add_css_class("monospace")
            val_lbl.set_xalign(0)
            self._facts_box.attach(val_lbl, col * 2 + 1, row, 1, 1)
            self._fact_labels[key] = val_lbl

            col += 1
            if col > 2:
                col = 0
                row += 1

    def update_facts(self, facts: Dict[str, str]):
        """Update fact values without rebuilding the grid."""
        for key, value in facts.items():
            if key in self._fact_labels:
                self._fact_labels[key].set_label(value)


class PerformancePage(Gtk.Box):
    """
    Mission Center-style performance dashboard.
    LEFT: device list  |  CENTER+RIGHT: graph + facts
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._devices: Dict[str, DeviceListItem] = {}
        self._device_meta: Dict[str, Dict[str, Any]] = {}
        self._selected_device: str = "cpu"
        self._build_ui()

    def _build_ui(self):
        # ── LEFT: Device rail ──
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        left_scroll.set_size_request(200, -1)
        self.append(left_scroll)

        self._device_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._device_list.set_margin_top(12)
        self._device_list.set_margin_bottom(12)
        left_scroll.set_child(self._device_list)

        # Section headers + devices
        self._add_section("System")
        self._add_device("cpu", "CPU", "computer-symbolic", (0.13, 0.77, 0.37))
        self._add_device("memory", "Memory", "drive-harddisk-symbolic", (0.48, 0.23, 0.93))
        self._add_device("swap", "Swap", "media-removable-symbolic", (0.96, 0.62, 0.04))
        self._add_device("thermals", "Thermals", "temperature-symbolic", (0.93, 0.27, 0.27))

        self._add_section("Compute")
        self._add_device("gpu_ada", "RTX 4000 Ada", "video-display-symbolic", (0.13, 0.59, 0.95))
        self._add_device("gpu_w5700x", "W5700X", "video-display-symbolic", (0.93, 0.27, 0.27))
        self._add_device("gpu_6900xt", "RX 6900 XT", "video-display-symbolic", (0.58, 0.30, 0.95))

        self._add_section("Storage")
        self._add_device("root", "Root", "drive-harddisk-system-symbolic", (0.20, 0.80, 0.60))
        self._add_device("work", "Work", "folder-symbolic", (0.13, 0.59, 0.95))
        self._add_device("nvme", "NVMe", "drive-harddisk-symbolic", (0.58, 0.30, 0.95))

        self._add_section("Network")
        self._add_device("network", "Network", "network-wireless-symbolic", (0.13, 0.77, 0.37))

        self._add_section("Agents")
        self._add_device("agents", "Agents", "applications-games-symbolic", (0.96, 0.62, 0.04))
        self._add_device("mcp", "MCP", "preferences-system-symbolic", (0.48, 0.23, 0.93))

        self._add_section("Proof")
        self._add_device("proof_browser", "Browser", "web-browser-symbolic", (0.21, 0.82, 0.50))

        # ── CENTER+RIGHT: Detail view ──
        self._detail = DeviceDetailView()
        self._detail.set_hexpand(True)
        self.append(self._detail)

        # Add CSS for selection
        self._setup_css()

        # Select first device after the detail view exists.
        self._select_device("cpu")

    def _setup_css(self):
        css = """
        .device-list-item {
            border-radius: 6px;
            padding: 6px 8px;
        }
        .device-list-item:hover {
            background-color: alpha(@moc_surface_3, 0.5);
        }
        .device-list-item.selected {
            background-color: alpha(@moc_surface_3, 0.85);
            border-left: 3px solid @moc_cyan;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _add_section(self, title: str):
        lbl = Gtk.Label(label=title)
        lbl.add_css_class("caption")
        lbl.set_xalign(0)
        lbl.set_margin_top(10)
        lbl.set_margin_start(8)
        lbl.set_margin_bottom(2)
        lbl.set_opacity(0.6)
        self._device_list.append(lbl)

    def _add_device(self, device_id: str, name: str, icon: str, color: Tuple[float, float, float]):
        item = DeviceListItem(device_id, name, icon, color)
        item.set_hexpand(True)
        # Make clickable
        gesture = Gtk.GestureClick()
        gesture.connect("pressed", lambda _g, _n, _x, _y: self._select_device(device_id))
        item.add_controller(gesture)
        self._devices[device_id] = item
        self._device_meta[device_id] = {"name": name, "color": color, "icon": icon}
        self._device_list.append(item)

    def _select_device(self, device_id: str):
        self._selected_device = device_id
        for did, item in self._devices.items():
            if did == device_id:
                item.add_css_class("selected")
            else:
                item.remove_css_class("selected")

        meta = self._device_meta.get(device_id, {})
        coll = get_collector()
        history = coll.get(self._collector_metric(device_id))
        self._detail.show_device(device_id, meta.get("name", device_id), history, {}, meta.get("color"))

    def _collector_metric(self, device_id: str) -> str:
        """Map UI device ids onto TelemetryCollector metric keys."""
        return {
            "gpu_ada": "gpu0",
            "gpu_w5700x": "gpu1",
            "gpu_6900xt": "gpu2",
            "root": "nvme",
            "work": "nvme",
        }.get(device_id, device_id)

    def update(self, data: dict):
        perf = data.get("performance") or {}
        if not perf:
            return

        coll = get_collector()
        status = "healthy"

        # ── System ──
        cpu = perf.get("cpu", {})
        cpu_util = cpu.get("utilPct", 0)
        load1 = cpu.get("load1", 0)
        if "cpu" in self._devices:
            status = "blocked" if cpu_util > 80 else "warn" if cpu_util > 60 else "healthy"
            self._devices["cpu"].set_value(f"{cpu_util:.0f}%", status)
            if self._selected_device == "cpu":
                self._detail.update_facts({
                    "Utilization": f"{cpu_util:.1f}%",
                    "Load 1m": f"{load1:.2f}",
                    "Load 5m": f"{cpu.get('load5', 0):.2f}",
                    "Load 15m": f"{cpu.get('load15', 0):.2f}",
                })

        mem = data.get("hostMemory", {}).get("ram", {})
        used_gb = mem.get("usedGb", 0)
        total_gb = mem.get("totalGb", 1)
        pct = (used_gb / total_gb * 100) if total_gb > 0 else 0
        if "memory" in self._devices:
            status = "blocked" if pct > 90 else "warn" if pct > 75 else "healthy"
            self._devices["memory"].set_value(f"{pct:.0f}%", status)
            if self._selected_device == "memory":
                self._detail.update_facts({
                    "Used": f"{used_gb:.1f} GB",
                    "Total": f"{total_gb:.0f} GB",
                    "Percent": f"{pct:.1f}%",
                })

        swap = data.get("hostMemory", {}).get("swap", {})
        swap_used = swap.get("usedGb", 0)
        swap_total = swap.get("totalGb", 1)
        swap_pct = (swap_used / swap_total * 100) if swap_total > 0 else 0
        if "swap" in self._devices:
            status = "blocked" if swap_pct > 80 else "warn" if swap_pct > 50 else "healthy"
            self._devices["swap"].set_value(f"{swap_pct:.0f}%", status)
            if self._selected_device == "swap":
                self._detail.update_facts({
                    "Used": f"{swap_used:.1f} GB",
                    "Total": f"{swap_total:.0f} GB",
                })

        temps = data.get("idle_health", {}).get("temperature", {})
        hottest = temps.get("hottest_c", 0)
        if "thermals" in self._devices:
            status = "blocked" if hottest > 85 else "warn" if hottest > 70 else "healthy"
            self._devices["thermals"].set_value(f"{hottest:.0f}°C", status)
            if self._selected_device == "thermals":
                self._detail.update_facts({
                    "Hottest": f"{hottest:.0f}°C",
                    "CPU": f"{temps.get('cpu_c', 0):.0f}°C",
                    "GPU max": f"{temps.get('gpu_max_c', 0):.0f}°C",
                    "NVMe max": f"{temps.get('nvme_max_c', 0):.0f}°C",
                })

        # ── Compute (GPUs) ──
        gpu_data = perf.get("gpu", {})
        gpus = gpu_data.get("gpus", [])
        gpu_map = {
            "gpu_ada": lambda n: "RTX 4000" in n or "RTX A4000" in n,
            "gpu_w5700x": lambda n: "W5700X" in n or "Radeon Pro" in n,
            "gpu_6900xt": lambda n: "RX 6900 XT" in n,
        }
        for i, gpu in enumerate(gpus):
            name = gpu.get("name", "")
            util = gpu.get("utilPct", 0)
            temp = gpu.get("tempC", 0)
            vram_used = gpu.get("vramUsedMiB", 0)
            vram_total = gpu.get("vramTotalMiB", 1)
            vram_gb = vram_used / 1024
            vram_total_gb = vram_total / 1024
            status = "blocked" if util > 95 else "warn" if util > 80 else "healthy"

            for did, matcher in gpu_map.items():
                if matcher(name):
                    self._devices[did].set_value(f"{util:.0f}%", status)
                    if self._selected_device == did:
                        self._detail.update_facts({
                            "Utilization": f"{util:.0f}%",
                            "Temperature": f"{temp}°C",
                            "VRAM used": f"{vram_gb:.1f} GB",
                            "VRAM total": f"{vram_total_gb:.0f} GB",
                            "Name": name,
                        })
                    break

        # ── Storage ──
        root = data.get("storage", {}).get("root", {})
        if "root" in self._devices and root:
            used = root.get("used_gb", 0)
            total = root.get("total_gb", 1)
            pct = root.get("used_pct", (used / total * 100) if total > 0 else 0)
            status = "blocked" if pct > 90 else "warn" if pct > 75 else "healthy"
            self._devices["root"].set_value(f"{pct:.0f}%", status)
            if self._selected_device == "root":
                self._detail.update_facts({
                    "Used": f"{used:.0f} GB",
                    "Total": f"{total:.0f} GB",
                    "Percent": f"{pct:.1f}%",
                })

        work = data.get("storage", {}).get("work", {})
        if "work" in self._devices and work:
            used = work.get("used_gb", 0)
            total = work.get("total_gb", 1)
            pct = work.get("used_pct", (used / total * 100) if total > 0 else 0)
            status = "blocked" if pct > 90 else "warn" if pct > 75 else "healthy"
            self._devices["work"].set_value(f"{pct:.0f}%", status)
            if self._selected_device == "work":
                self._detail.update_facts({
                    "Used": f"{used:.0f} GB",
                    "Total": f"{total:.0f} GB",
                    "Percent": f"{pct:.1f}%",
                })

        nvme = perf.get("nvme", {})
        devices = nvme.get("devices", [])
        total_ops = sum(
            (d.get("readOps", d.get("reads", 0)) or 0) +
            (d.get("writeOps", d.get("writes", 0)) or 0)
            for d in devices
        )
        if "nvme" in self._devices:
            self._devices["nvme"].set_value(f"{total_ops:,}", "healthy")
            if self._selected_device == "nvme":
                self._detail.update_facts({
                    "Total ops": f"{total_ops:,}",
                    "Devices": str(len(devices)),
                })

        # ── Network ──
        net = perf.get("network", {})
        interfaces = net.get("interfaces", [])
        total_mb = sum(
            (d.get("rxMiB", 0) or (d.get("rxBytes", 0) or 0) / (1024 * 1024)) +
            (d.get("txMiB", 0) or (d.get("txBytes", 0) or 0) / (1024 * 1024))
            for d in interfaces
        )
        if "network" in self._devices:
            self._devices["network"].set_value(f"{total_mb:.0f} MB", "healthy")
            if self._selected_device == "network":
                self._detail.update_facts({
                    "Total": f"{total_mb:.0f} MB",
                    "Interfaces": str(len(interfaces)),
                })

        # ── Agents ──
        agents = perf.get("agents", {})
        total = agents.get("total", 0)
        abandoned = agents.get("abandoned", 0)
        if "agents" in self._devices:
            status = "blocked" if abandoned > 5 else "warn" if abandoned > 0 else "healthy"
            self._devices["agents"].set_value(str(total), status)
            if self._selected_device == "agents":
                self._detail.update_facts({
                    "Total": str(total),
                    "Abandoned": str(abandoned),
                })

        mcp = perf.get("mcp", {})
        mcp_total = mcp.get("total", 0)
        if "mcp" in self._devices:
            status = "blocked" if mcp_total > 80 else "warn" if mcp_total > 50 else "healthy"
            self._devices["mcp"].set_value(str(mcp_total), status)
            if self._selected_device == "mcp":
                self._detail.update_facts({
                    "Total": str(mcp_total),
                })

        # ── Proof Browser (helper-only CDP read) ──
        browser = data.get("proofBrowser") or {}
        if "proof_browser" in self._devices:
            ok = browser.get("ok", False)
            target_count = browser.get("target_count", 0)
            teacher_tabs = browser.get("teacher_studio_tabs", 0)
            status = "healthy" if ok and target_count > 0 else "warn" if ok else "blocked"
            self._devices["proof_browser"].set_value(str(target_count), status)
            if self._selected_device == "proof_browser":
                self._detail.update_facts({
                    "CDP port": str(browser.get("port", "?")),
                    "Targets": str(target_count),
                    "Pages": str(browser.get("page_count", 0)),
                    "Current URL": browser.get("current_url", "")[:60],
                    "Current title": browser.get("current_title", "")[:40],
                    "Teacher-studio tabs": str(teacher_tabs),
                    "Note": browser.get("note", ""),
                })
