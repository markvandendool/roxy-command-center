#!/usr/bin/env python3
"""
GPU card widget with telemetry display.
ROXY-CMD-STORY-011: VRAM/temp/util/power display with pool badge.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
from typing import Optional, Dict, Any
from collections import deque

class GPUCard(Gtk.Box):
    """
    GPU monitoring card showing telemetry.
    
    Shows:
    - GPU name and pool badge
    - VRAM usage bar
    - Temperature with color coding
    - Utilization percentage
    - Power draw
    """
    
    def __init__(self, gpu_index: int = 0, gpu_name: str = "GPU"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        self.gpu_index = gpu_index
        self.gpu_name = gpu_name
        self._pool: Optional[str] = None
        
        # History for graphs (60 data points = 60s at 1s interval)
        self.temp_history = deque(maxlen=60)
        self.vram_history = deque(maxlen=60)
        self.util_history = deque(maxlen=60)
        
        # Card styling
        self.add_css_class("card")
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_margin_top(12)
        header.set_margin_start(12)
        header.set_margin_end(12)
        
        # GPU icon
        icon = Gtk.Image.new_from_icon_name("application-x-firmware-symbolic")
        icon.set_pixel_size(24)
        header.append(icon)
        
        # Name
        self.name_label = Gtk.Label(label=gpu_name)
        self.name_label.add_css_class("title-3")
        self.name_label.set_halign(Gtk.Align.START)
        self.name_label.set_hexpand(True)
        header.append(self.name_label)
        
        # Pool badge
        self.pool_badge = Gtk.Label()
        self.pool_badge.add_css_class("pill")
        header.append(self.pool_badge)
        
        self.append(header)
        
        # Stats grid
        stats_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        stats_box.set_margin_top(8)
        stats_box.set_margin_bottom(12)
        stats_box.set_margin_start(12)
        stats_box.set_margin_end(12)
        
        # VRAM bar
        vram_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vram_label = Gtk.Label(label="VRAM")
        vram_label.set_halign(Gtk.Align.START)
        vram_label.set_size_request(60, -1)
        vram_row.append(vram_label)
        
        self.vram_bar = Gtk.ProgressBar()
        self.vram_bar.set_hexpand(True)
        self.vram_bar.set_show_text(True)
        vram_row.append(self.vram_bar)
        stats_box.append(vram_row)
        
        # Temperature row
        temp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        temp_label = Gtk.Label(label="Temp")
        temp_label.set_halign(Gtk.Align.START)
        temp_label.set_size_request(60, -1)
        temp_row.append(temp_label)
        
        self.temp_value = Gtk.Label()
        self.temp_value.set_halign(Gtk.Align.START)
        self.temp_value.set_hexpand(True)
        temp_row.append(self.temp_value)
        stats_box.append(temp_row)
        
        # Utilization row
        util_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        util_label = Gtk.Label(label="Util")
        util_label.set_halign(Gtk.Align.START)
        util_label.set_size_request(60, -1)
        util_row.append(util_label)
        
        self.util_bar = Gtk.ProgressBar()
        self.util_bar.set_hexpand(True)
        self.util_bar.set_show_text(True)
        util_row.append(self.util_bar)
        stats_box.append(util_row)
        
        # Power row
        power_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        power_label = Gtk.Label(label="Power")
        power_label.set_halign(Gtk.Align.START)
        power_label.set_size_request(60, -1)
        power_row.append(power_label)
        
        self.power_value = Gtk.Label()
        self.power_value.set_halign(Gtk.Align.START)
        self.power_value.set_hexpand(True)
        power_row.append(self.power_value)
        stats_box.append(power_row)
        
        self.append(stats_box)
        
        # Initialize with empty state
        self.set_values(0, 0, 0, 0, 0)
    
    def set_pool(self, pool: Optional[str]):
        """Set the pool assignment (BIG/FAST)."""
        self._pool = pool
        
        if pool:
            self.pool_badge.set_text(pool.upper())
            self.pool_badge.set_visible(True)
            
            # Apply pool-specific styling
            self.pool_badge.remove_css_class("accent-big")
            self.pool_badge.remove_css_class("accent-fast")
            
            if pool.lower() == "big":
                self.pool_badge.add_css_class("accent-big")  # Red
            elif pool.lower() == "fast":
                self.pool_badge.add_css_class("accent-fast")  # Blue
        else:
            self.pool_badge.set_visible(False)
    
    def set_values(self, vram_used: float, vram_total: float, 
                   temp: float, util: float, power: float):
        """Update GPU values."""
        # VRAM
        vram_percent = (vram_used / vram_total * 100) if vram_total > 0 else 0
        self.vram_bar.set_fraction(vram_percent / 100.0)
        self.vram_bar.set_text(f"{vram_used:.1f} / {vram_total:.1f} GB ({vram_percent:.0f}%)")
        self._apply_usage_style(self.vram_bar, vram_percent)
        
        # Temperature with color coding
        self.temp_value.set_text(f"{temp:.0f}°C")
        self.temp_value.remove_css_class("success")
        self.temp_value.remove_css_class("warning")
        self.temp_value.remove_css_class("error")
        
        if temp >= 80:
            self.temp_value.add_css_class("error")
        elif temp >= 60:
            self.temp_value.add_css_class("warning")
        else:
            self.temp_value.add_css_class("success")
        
        # Utilization
        self.util_bar.set_fraction(util / 100.0)
        self.util_bar.set_text(f"{util:.0f}%")
        self._apply_usage_style(self.util_bar, util)
        
        # Power
        self.power_value.set_text(f"{power:.0f} W")
        
        # Store history for graphs
        self.temp_history.append(temp)
        self.vram_history.append(vram_percent)
        self.util_history.append(util)
    
    def update_from_daemon(self, gpu_data: dict):
        """Update from daemon GPU data."""
        if not gpu_data:
            return
        
        # Extract values - handle both naming conventions
        vram_used = gpu_data.get("vram_used_gb", 0)
        vram_total = gpu_data.get("vram_total_gb", 16)
        temp = gpu_data.get("temp_c", gpu_data.get("temp", 0))
        util = gpu_data.get("utilization_pct", gpu_data.get("utilization", 0))
        power = gpu_data.get("power_w", 0)
        
        # Update name if available
        name = gpu_data.get("name", self.gpu_name)
        if name != self.gpu_name:
            self.gpu_name = name
            self.name_label.set_text(name)
        
        # Detect pool from index (6900 XT = BIG, W5700X = FAST)
        # This is a heuristic - could be improved with explicit mapping
        if "6900" in name:
            self.set_pool("BIG")
        elif "5700" in name or "W5700" in name:
            self.set_pool("FAST")
        
        self.set_values(vram_used, vram_total, temp, util, power)
    
    def update(self, gpu_data: dict):
        """Alias for update_from_daemon - compatibility method."""
        self.update_from_daemon(gpu_data)
    
    def _apply_usage_style(self, bar: Gtk.ProgressBar, percent: float):
        """Apply color styling based on usage level."""
        bar.remove_css_class("success")
        bar.remove_css_class("warning")
        bar.remove_css_class("error")
        
        if percent >= 90:
            bar.add_css_class("error")
        elif percent >= 70:
            bar.add_css_class("warning")
        # No success class for normal usage
