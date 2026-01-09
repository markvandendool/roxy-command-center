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
            self._sparkline = SparklineWidget(history_size=30)
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
        
        # System stats row
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
    
    def _navigate(self, page: str):
        """Navigate to a page."""
        if self.on_navigate:
            self.on_navigate(page)
    
    def update(self, data: dict):
        """Update all cards with daemon data."""
        system = data.get("system", {})
        gpus = data.get("gpus", [])
        services = data.get("services", {})
        ollama = data.get("ollama", {})
        
        # CPU
        cpu_percent = system.get("cpu_percent", 0)
        load_avg = system.get("load_avg", [0, 0, 0])
        if "cpu" in self._cards:
            self._cards["cpu"].set_value(f"{cpu_percent:.0f}%")
            self._cards["cpu"].set_subtitle(f"Load: {load_avg[0]:.1f}")
            self._cards["cpu"].add_sparkline_value(cpu_percent)
        
        # Memory
        mem_used = system.get("mem_used_gb", 0)
        mem_total = system.get("mem_total_gb", 1)
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
                temp = gpu.get("temp", 0)
                vram_used = gpu.get("vram_used_gb", 0)
                vram_total = gpu.get("vram_total_gb", 1)
                vram_percent = (vram_used / vram_total * 100) if vram_total > 0 else 0
                pool = gpu.get("pool", "")
                
                # Truncate name
                if len(name) > 20:
                    name = name[:17] + "..."
                
                card.set_value(f"{temp}°C")
                card.set_subtitle(f"{vram_used:.1f}/{vram_total:.0f} GB VRAM")
                card.add_sparkline_value(temp)
                
                # Color by temp
                if temp >= 80:
                    card.set_sparkline_color(0.937, 0.267, 0.267)  # Red
                elif temp >= 60:
                    card.set_sparkline_color(0.961, 0.620, 0.043)  # Orange
                else:
                    card.set_sparkline_color(0.133, 0.773, 0.369)  # Green
        
        # Ollama
        loaded_models = ollama.get("loaded_models", [])
        pools = ollama.get("pools", {})
        if "ollama" in self._cards:
            model_count = len(loaded_models)
            self._cards["ollama"].set_value(f"{model_count} loaded")
            
            pool_info = []
            for pool_name, pool_data in pools.items():
                models = pool_data.get("models", [])
                pool_info.append(f"{pool_name}: {len(models)}")
            self._cards["ollama"].set_subtitle(" / ".join(pool_info) if pool_info else "No pools")
        
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
            alert_count = alert_manager.get_alert_count()
            critical_count = alert_manager.get_alert_count(AlertSeverity.CRITICAL)
            
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
