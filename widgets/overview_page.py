#!/usr/bin/env python3
"""
Overview page with dashboard cards.
ROXY-CMD-STORY-013, ROXY-CMD-STORY-014: Overview dashboard.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any

from widgets.graph_widget import SparklineWidget, GraphConfig
from services.alert_manager import get_alert_manager, AlertSeverity


class OverviewCard(Gtk.Box):
    """
    A dashboard card showing a metric.
    
    Features:
    - Large value display
    - Subtitle/label
    - Optional sparkline
    - Click navigation
    """
    
    def __init__(
        self,
        title: str,
        icon_name: str = "",
        show_sparkline: bool = False,
        on_click: Optional[callable] = None
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("overview-card")
        
        self.on_click = on_click
        self._sparkline: Optional[SparklineWidget] = None
        
        # Make clickable
        if on_click:
            click = Gtk.GestureClick()
            click.connect("pressed", self._on_clicked)
            self.add_controller(click)
            self.set_cursor_from_name("pointer")
        
        # Header with icon and title
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(header)
        
        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(20)
            icon.add_css_class("dim-label")
            header.append(icon)
        
        title_label = Gtk.Label(label=title)
        title_label.add_css_class("overview-title")
        title_label.add_css_class("dim-label")
        title_label.set_xalign(0)
        header.append(title_label)
        
        # Value display
        self.value_label = Gtk.Label(label="--")
        self.value_label.add_css_class("overview-value")
        self.value_label.set_xalign(0)
        self.append(self.value_label)
        
        # Subtitle
        self.subtitle_label = Gtk.Label(label="")
        self.subtitle_label.add_css_class("overview-subtitle")
        self.subtitle_label.add_css_class("dim-label")
        self.subtitle_label.set_xalign(0)
        self.append(self.subtitle_label)
        
        # Sparkline
        if show_sparkline:
            self._sparkline = SparklineWidget()
            self._sparkline.set_margin_top(8)
            self.append(self._sparkline)
    
    def set_value(self, value: str):
        """Set the main value."""
        self.value_label.set_label(value)
    
    def set_subtitle(self, text: str):
        """Set the subtitle."""
        self.subtitle_label.set_label(text)
    
    def add_sparkline_value(self, value: float):
        """Add a value to the sparkline."""
        if self._sparkline:
            self._sparkline.add_value(value)
    
    def set_sparkline_color(self, r: float, g: float, b: float):
        """Set sparkline color."""
        if self._sparkline:
            self._sparkline._color = (r, g, b)
            self._sparkline.queue_draw()
    
    def _on_clicked(self, gesture, n_press, x, y):
        """Handle click."""
        if self.on_click:
            self.on_click()


class OverviewPage(Gtk.ScrolledWindow):
    """
    Overview dashboard with summary cards.
    
    Features:
    - System stats cards
    - GPU cards
    - Service health
    - Alert summary
    - Quick navigation
    """
    
    def __init__(self, on_navigate: Optional[callable] = None):
        super().__init__()
        self.on_navigate = on_navigate
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self._cards: Dict[str, OverviewCard] = {}
        self._build_ui()
    
    def _build_ui(self):
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)
        
        # Title
        title = Gtk.Label(label="System Overview")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)
        
        # Review-only posture labels
        posture_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        posture_box.set_margin_top(4)
        main_box.append(posture_box)
        for text in ("Read-only", "Manual snapshot", "No background polling", "ROXY quiet baseline"):
            label = Gtk.Label(label=text)
            label.add_css_class("caption")
            label.add_css_class("source-badge")
            label.add_css_class("source-daemon")
            posture_box.append(label)

        # Law 0 / quiet-state row
        quiet_title = Gtk.Label(label="Quiet Baseline")
        quiet_title.add_css_class("title-3")
        quiet_title.set_xalign(0)
        quiet_title.set_margin_top(8)
        main_box.append(quiet_title)

        quiet_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        quiet_box.set_homogeneous(True)
        main_box.append(quiet_box)

        law0_card = OverviewCard("Law 0", "security-high-symbolic")
        self._cards["law0"] = law0_card
        quiet_box.append(law0_card)

        guard_card = OverviewCard("External Guard", "drive-removable-media-symbolic")
        self._cards["external_guard"] = guard_card
        quiet_box.append(guard_card)

        idle_card = OverviewCard("CPU Idle", "utilities-system-monitor-symbolic", show_sparkline=True)
        self._cards["cpu_idle"] = idle_card
        quiet_box.append(idle_card)

        thermal_card = OverviewCard("Thermal", "temperature-symbolic")
        self._cards["thermal"] = thermal_card
        quiet_box.append(thermal_card)

        # Storage identity row
        storage_title = Gtk.Label(label="Storage Identity")
        storage_title.add_css_class("title-3")
        storage_title.set_xalign(0)
        storage_title.set_margin_top(16)
        main_box.append(storage_title)

        storage_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        storage_box.set_homogeneous(True)
        main_box.append(storage_box)

        root_card = OverviewCard("Root", "drive-harddisk-system-symbolic")
        self._cards["root_disk"] = root_card
        storage_box.append(root_card)

        work_card = OverviewCard("Work", "drive-harddisk-symbolic")
        self._cards["work_disk"] = work_card
        storage_box.append(work_card)

        p51_card = OverviewCard("P51 Vault", "media-flash-symbolic")
        self._cards["p51"] = p51_card
        storage_box.append(p51_card)

        safety_card = OverviewCard("ROXY_SAFETY", "dialog-warning-symbolic")
        self._cards["roxy_safety"] = safety_card
        storage_box.append(safety_card)

        # System stats row
        stats_title = Gtk.Label(label="System Load")
        stats_title.add_css_class("title-3")
        stats_title.set_xalign(0)
        stats_title.set_margin_top(16)
        main_box.append(stats_title)

        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        stats_box.set_homogeneous(True)
        main_box.append(stats_box)
        
        # CPU card
        cpu_card = OverviewCard(
            "CPU",
            "computer-symbolic",
            show_sparkline=True,
            on_click=lambda: self._navigate("overview")
        )
        self._cards["cpu"] = cpu_card
        stats_box.append(cpu_card)
        
        # Memory card
        mem_card = OverviewCard(
            "Memory",
            "drive-harddisk-symbolic",
            show_sparkline=True,
            on_click=lambda: self._navigate("overview")
        )
        self._cards["memory"] = mem_card
        stats_box.append(mem_card)
        
        # GPU section title
        gpu_title = Gtk.Label(label="GPUs")
        gpu_title.add_css_class("title-3")
        gpu_title.set_xalign(0)
        gpu_title.set_margin_top(16)
        main_box.append(gpu_title)
        
        # GPU cards container
        self.gpu_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.gpu_box.set_homogeneous(True)
        main_box.append(self.gpu_box)
        
        # Placeholder GPU cards (will be populated by update)
        for i in range(2):
            card = OverviewCard(
                f"GPU {i}",
                "video-display-symbolic",
                show_sparkline=True,
                on_click=lambda: self._navigate("gpus")
            )
            self._cards[f"gpu{i}"] = card
            self.gpu_box.append(card)
        
        # Services section
        services_title = Gtk.Label(label="Services")
        services_title.add_css_class("title-3")
        services_title.set_xalign(0)
        services_title.set_margin_top(16)
        main_box.append(services_title)
        
        services_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        services_box.set_homogeneous(True)
        main_box.append(services_box)
        
        # Ollama card
        ollama_card = OverviewCard(
            "Ollama",
            "face-smile-big-symbolic",
            on_click=lambda: self._navigate("ollama")
        )
        self._cards["ollama"] = ollama_card
        services_box.append(ollama_card)

        # Docker card
        docker_card = OverviewCard(
            "Docker",
            "applications-system-symbolic",
            on_click=lambda: self._navigate("services")
        )
        self._cards["docker"] = docker_card
        services_box.append(docker_card)
        
        # Services health card
        health_card = OverviewCard(
            "Service Health",
            "system-run-symbolic",
            on_click=lambda: self._navigate("services")
        )
        self._cards["services"] = health_card
        services_box.append(health_card)
        
        # Alerts card
        alerts_card = OverviewCard(
            "Active Alerts",
            "dialog-warning-symbolic",
            on_click=lambda: self._navigate("alerts")
        )
        self._cards["alerts"] = alerts_card
        services_box.append(alerts_card)

        # SMART watch note
        smart_card = OverviewCard("Samsung SMART Watch", "dialog-information-symbolic")
        self._cards["smart_watch"] = smart_card
        main_box.append(smart_card)
    
    def _navigate(self, page: str):
        """Navigate to a page."""
        if self.on_navigate:
            self.on_navigate(page)
    
    def update(self, data: dict):
        """Update all cards with daemon data."""
        # Use normalized schema
        cpu_data = data.get("cpu", {})
        memory_data = data.get("memory", {})
        gpus = data.get("gpus", [])
        services = data.get("services", {})
        ollama = data.get("ollama", {})
        roxy = data.get("roxy", {})
        storage = data.get("storage", {})
        idle = data.get("idle_health", {})
        alerts = data.get("alerts", [])

        def set_pass_fail(card_key: str, ok: bool, good: str = "PASS", bad: str = "FAIL", subtitle: str = ""):
            if card_key not in self._cards:
                return
            card = self._cards[card_key]
            card.set_value(good if ok else bad)
            card.set_subtitle(subtitle)
            if ok:
                card.remove_css_class("status-warning")
                card.remove_css_class("status-critical")
            else:
                card.add_css_class("status-critical")

        def set_usage_card(card_key: str, volume: dict, expected: str):
            if card_key not in self._cards:
                return
            used_pct = volume.get("used_pct", 0.0)
            label = volume.get("label", expected)
            free_gb = volume.get("free_gb", 0.0)
            self._cards[card_key].set_value(f"{used_pct:.0f}%")
            self._cards[card_key].set_subtitle(f"{label} · {free_gb:.0f} GB free")
        
        # CPU - use normalized keys
        cpu_percent = cpu_data.get("cpu_pct", 0)
        load_1m = cpu_data.get("load_1m", 0)
        if "cpu" in self._cards:
            self._cards["cpu"].set_value(f"{cpu_percent:.0f}%")
            self._cards["cpu"].set_subtitle(f"Load: {load_1m:.1f}")
            self._cards["cpu"].add_sparkline_value(cpu_percent)

        # Law 0 / guard state
        set_pass_fail("law0", bool(roxy.get("law0_ok")), subtitle="Read-only gate")
        set_pass_fail("external_guard", bool(roxy.get("external_guard_ok")), subtitle="External media policy")

        # Idle health
        idle_pct = idle.get("cpu_idle_pct", 0.0)
        load_5m = idle.get("load_5m", 0.0)
        logical_cpus = idle.get("logical_cpus", 0)
        if "cpu_idle" in self._cards:
            self._cards["cpu_idle"].set_value(f"{idle_pct:.0f}%")
            self._cards["cpu_idle"].set_subtitle(f"Load {load_5m:.2f} / {logical_cpus} threads")
            self._cards["cpu_idle"].add_sparkline_value(idle_pct)

        temp = idle.get("temperature", {})
        hottest = temp.get("hottest_c", 0.0)
        thermal_status = temp.get("status", "unknown")
        if "thermal" in self._cards:
            self._cards["thermal"].set_value(thermal_status.title())
            self._cards["thermal"].set_subtitle(f"Hottest {hottest:.0f}°C")

        # Storage identity and guarded externals
        set_usage_card("root_disk", storage.get("root", {}), "ROXY_ROOT")
        set_usage_card("work_disk", storage.get("work", {}), "ROXY_WORK")
        externals = storage.get("externals", {})
        if "p51" in self._cards:
            p51_visible = bool(externals.get("p51_visible"))
            self._cards["p51"].set_value("Visible" if p51_visible else "Absent")
            self._cards["p51"].set_subtitle("Read-only source vault" if p51_visible else "USB vault not mounted")
        if "roxy_safety" in self._cards:
            safety_mounted = bool(externals.get("roxy_safety_mounted"))
            self._cards["roxy_safety"].set_value("Mounted" if safety_mounted else "Blocked")
            self._cards["roxy_safety"].set_subtitle("Unsafe: unmount now" if safety_mounted else "Not mounted / ignored")
            if safety_mounted:
                self._cards["roxy_safety"].add_css_class("status-critical")
            else:
                self._cards["roxy_safety"].remove_css_class("status-critical")
        
        # Memory - use normalized keys
        mem_used = memory_data.get("mem_used_gb", 0)
        mem_total = memory_data.get("mem_total_gb", 1)
        mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0
        if "memory" in self._cards:
            self._cards["memory"].set_value(f"{mem_used:.1f} GB")
            self._cards["memory"].set_subtitle(f"{mem_percent:.0f}% of {mem_total:.0f} GB")
            self._cards["memory"].add_sparkline_value(mem_percent)
        
        # GPUs
        for i, gpu in enumerate(gpus[:2]):  # Max 2 GPU cards
            card_key = f"gpu{i}"
            if card_key in self._cards:
                card = self._cards[card_key]
                
                name = gpu.get("name", f"GPU {i}")
                temp = gpu.get("temp_c", gpu.get("temp", 0))  # temp_c normalized, fallback temp
                vram_used = gpu.get("vram_used_gb", 0)
                vram_total = gpu.get("vram_total_gb", 1)
                vram_percent = (vram_used / vram_total * 100) if vram_total > 0 else 0
                util_pct = gpu.get("utilization_pct", gpu.get("utilization", 0))
                pool = gpu.get("pool", "")
                
                # Truncate name
                if len(name) > 20:
                    name = name[:17] + "..."
                
                card.set_value(f"{temp}°C")
                card.set_subtitle(f"{vram_used:.1f}/{vram_total:.0f} GB • {util_pct}%")
                card.add_sparkline_value(temp)
                
                # Color by temp
                if temp >= 80:
                    card.set_sparkline_color(0.937, 0.267, 0.267)  # Red
                elif temp >= 60:
                    card.set_sparkline_color(0.961, 0.620, 0.043)  # Orange
                else:
                    card.set_sparkline_color(0.133, 0.773, 0.369)  # Green
        
        # Ollama
        loaded_models = ollama.get("models", [])
        if "ollama" in self._cards:
            model_count = len(loaded_models)
            reachable = ollama.get("reachable", False)
            active = idle.get("ollama_active_workloads", 0)
            model_names = [m.get("name", "unknown") for m in loaded_models[:2]]
            self._cards["ollama"].set_value("Online" if reachable else "Offline")
            subtitle = f"{model_count} model · {active} active"
            if model_names:
                subtitle = f"{', '.join(model_names)} · {active} active"
            self._cards["ollama"].set_subtitle(subtitle)

        if "docker" in self._cards:
            docker = services.get("docker", {})
            count = idle.get("docker_container_count", 0)
            active = docker.get("active", False)
            self._cards["docker"].set_value(f"{count} running")
            self._cards["docker"].set_subtitle("/mnt/work/containers/docker" if active else "service inactive")
        
        # Services health
        if "services" in self._cards:
            healthy = 0
            unhealthy = 0
            for name, service in services.items():
                health = service.get("health", "unknown")
                if health in ("ok", "healthy"):
                    healthy += 1
                else:
                    unhealthy += 1
            
            total = healthy + unhealthy
            self._cards["services"].set_value(f"{healthy}/{total}")
            
            if unhealthy > 0:
                self._cards["services"].set_subtitle(f"{unhealthy} unhealthy")
                self._cards["services"].add_css_class("status-warning")
            else:
                self._cards["services"].set_subtitle("All healthy")
                self._cards["services"].remove_css_class("status-warning")
        
        # Alerts
        if "alerts" in self._cards:
            alert_manager = get_alert_manager()
            managed_alert_count = alert_manager.get_alert_count()
            managed_critical_count = alert_manager.get_alert_count(AlertSeverity.CRITICAL)
            payload_critical_count = len([a for a in alerts if a.get("level") == "error"])
            payload_warning_count = len([a for a in alerts if a.get("level") == "warning"])
            alert_count = managed_alert_count + len(alerts)
            critical_count = managed_critical_count + payload_critical_count
            
            self._cards["alerts"].set_value(str(alert_count))
            
            if critical_count > 0:
                self._cards["alerts"].set_subtitle(f"{critical_count} critical")
                self._cards["alerts"].add_css_class("status-critical")
            elif alert_count > 0:
                self._cards["alerts"].set_subtitle(f"{alert_count} warnings")
                self._cards["alerts"].add_css_class("status-warning")
            else:
                self._cards["alerts"].set_subtitle("All clear")
                self._cards["alerts"].remove_css_class("status-critical")
                self._cards["alerts"].remove_css_class("status-warning")

        if "smart_watch" in self._cards:
            failed_units = idle.get("failed_unit_count", 0)
            note = idle.get("samsung_smart_note", "")
            self._cards["smart_watch"].set_value("Watchlist")
            self._cards["smart_watch"].set_subtitle(f"{failed_units} failed units · {note}")
