#!/usr/bin/env python3
"""
System stats panel widget.
ROXY-CMD-STORY-006: CPU/RAM/Disk/Network detailed stats.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
from typing import Optional, Dict, Any

class SystemStatsPanel(Gtk.Box):
    """
    System statistics panel with detailed metrics.
    
    Shows:
    - CPU usage (overall and per-core)
    - Memory breakdown (used/cached/available)
    - Disk usage
    - Network traffic
    - Uptime
    """
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
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
        
        title = Gtk.Label(label="System")
        title.add_css_class("title-3")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        header.append(title)
        
        # Uptime badge
        self.uptime_badge = Gtk.Label()
        self.uptime_badge.add_css_class("pill")
        self.uptime_badge.add_css_class("dim-label")
        header.append(self.uptime_badge)
        
        self.append(header)
        
        # Stats grid
        stats_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        stats_box.set_margin_top(12)
        stats_box.set_margin_bottom(12)
        stats_box.set_margin_start(12)
        stats_box.set_margin_end(12)
        
        # CPU Section
        cpu_section = self._create_section("CPU")
        self.cpu_bar = self._create_progress_row("Overall", 0)
        cpu_section.append(self.cpu_bar)
        
        self.load_label = Gtk.Label(label="Load: 0.00, 0.00, 0.00")
        self.load_label.add_css_class("dim-label")
        self.load_label.set_halign(Gtk.Align.START)
        cpu_section.append(self.load_label)
        
        stats_box.append(cpu_section)
        
        # Memory Section
        mem_section = self._create_section("Memory")
        self.mem_bar = self._create_progress_row("Used", 0)
        mem_section.append(self.mem_bar)
        
        self.mem_details = Gtk.Label()
        self.mem_details.add_css_class("dim-label")
        self.mem_details.set_halign(Gtk.Align.START)
        mem_section.append(self.mem_details)
        
        stats_box.append(mem_section)
        
        # Disk Section
        disk_section = self._create_section("Disk")
        self.disk_bar = self._create_progress_row("Used", 0)
        disk_section.append(self.disk_bar)
        
        self.disk_details = Gtk.Label()
        self.disk_details.add_css_class("dim-label")
        self.disk_details.set_halign(Gtk.Align.START)
        disk_section.append(self.disk_details)
        
        stats_box.append(disk_section)
        
        # Network Section (optional)
        net_section = self._create_section("Network")
        self.net_label = Gtk.Label(label="↓ 0 KB/s  ↑ 0 KB/s")
        self.net_label.set_halign(Gtk.Align.START)
        net_section.append(self.net_label)
        
        stats_box.append(net_section)
        
        self.append(stats_box)
    
    def _create_section(self, title: str) -> Gtk.Box:
        """Create a labeled section."""
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        
        label = Gtk.Label(label=title)
        label.add_css_class("heading")
        label.set_halign(Gtk.Align.START)
        section.append(label)
        
        return section
    
    def _create_progress_row(self, label: str, value: float) -> Gtk.Box:
        """Create a labeled progress bar row."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        name = Gtk.Label(label=label)
        name.set_halign(Gtk.Align.START)
        name.set_size_request(60, -1)
        row.append(name)
        
        bar = Gtk.ProgressBar()
        bar.set_fraction(value / 100.0 if value <= 100 else value)
        bar.set_hexpand(True)
        bar.set_show_text(True)
        bar.set_text(f"{value:.1f}%")
        row.append(bar)
        
        # Store reference to bar for updates
        row.progress_bar = bar
        
        return row
    
    def update_from_daemon(self, data: dict):
        """Update stats from daemon response."""
        system = data.get("system", {})
        
        # CPU
        cpu_percent = system.get("cpu_percent", 0)
        self.cpu_bar.progress_bar.set_fraction(cpu_percent / 100.0)
        self.cpu_bar.progress_bar.set_text(f"{cpu_percent:.1f}%")
        
        # Apply color based on usage
        self._apply_usage_style(self.cpu_bar.progress_bar, cpu_percent)
        
        # Load average
        load_avg = system.get("load_avg", [0, 0, 0])
        if isinstance(load_avg, list) and len(load_avg) >= 3:
            self.load_label.set_text(f"Load: {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}")
        elif isinstance(load_avg, (int, float)):
            self.load_label.set_text(f"Load: {load_avg:.2f}")
        
        # Memory
        mem_used = system.get("mem_used_gb", 0)
        mem_total = system.get("mem_total_gb", 1)
        mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0
        
        self.mem_bar.progress_bar.set_fraction(mem_percent / 100.0)
        self.mem_bar.progress_bar.set_text(f"{mem_used:.1f} / {mem_total:.1f} GB ({mem_percent:.0f}%)")
        self._apply_usage_style(self.mem_bar.progress_bar, mem_percent)
        
        mem_cached = system.get("mem_cached_gb", 0)
        mem_available = system.get("mem_available_gb", mem_total - mem_used)
        self.mem_details.set_text(f"Cached: {mem_cached:.1f} GB | Available: {mem_available:.1f} GB")
        
        # Disk
        disk_used = system.get("disk_used_gb", 0)
        disk_total = system.get("disk_total_gb", 1)
        disk_percent = (disk_used / disk_total * 100) if disk_total > 0 else 0
        
        self.disk_bar.progress_bar.set_fraction(disk_percent / 100.0)
        self.disk_bar.progress_bar.set_text(f"{disk_used:.0f} / {disk_total:.0f} GB ({disk_percent:.0f}%)")
        self._apply_usage_style(self.disk_bar.progress_bar, disk_percent)
        
        disk_free = disk_total - disk_used
        self.disk_details.set_text(f"Free: {disk_free:.0f} GB")
        
        # Network (if available)
        net_rx = system.get("net_rx_kbps", 0)
        net_tx = system.get("net_tx_kbps", 0)
        self.net_label.set_text(f"↓ {self._format_speed(net_rx)}  ↑ {self._format_speed(net_tx)}")
        
        # Uptime
        uptime = system.get("uptime", "")
        if uptime:
            self.uptime_badge.set_text(f"Up: {uptime}")
        else:
            uptime_seconds = system.get("uptime_seconds", 0)
            if uptime_seconds:
                self.uptime_badge.set_text(f"Up: {self._format_uptime(uptime_seconds)}")
    
    def _apply_usage_style(self, bar: Gtk.ProgressBar, percent: float):
        """Apply color styling based on usage level."""
        bar.remove_css_class("success")
        bar.remove_css_class("warning")
        bar.remove_css_class("error")
        
        if percent >= 90:
            bar.add_css_class("error")
        elif percent >= 70:
            bar.add_css_class("warning")
        else:
            bar.add_css_class("success")
    
    def _format_speed(self, kbps: float) -> str:
        """Format network speed."""
        if kbps >= 1024:
            return f"{kbps / 1024:.1f} MB/s"
        return f"{kbps:.0f} KB/s"
    
    def _format_uptime(self, seconds: int) -> str:
        """Format uptime from seconds."""
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        
        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
