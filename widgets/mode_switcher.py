#!/usr/bin/env python3
"""
Mode switcher widget for local/remote/auto mode selection.
ROXY-CMD-STORY-005: Mode configuration and source display.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Callable
import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".config/roxy-command-center/config.json"

class ModeSwitcher(Gtk.Box):
    """
    Mode switcher widget for selecting local/remote/auto modes.
    
    Shows:
    - Mode dropdown (local/remote/auto)
    - Current source indicator
    - Remote host configuration
    - Connection status
    - Error messages
    """
    
    def __init__(self, on_mode_changed: Optional[Callable[[str], None]] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        self.on_mode_changed = on_mode_changed
        self._current_mode = "auto"
        self._current_source = "unknown"
        self._remote_host = "10.0.0.69"
        self._remote_port = 8766
        self._remote_error: Optional[str] = None
        
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
        
        title = Gtk.Label(label="System Mode")
        title.add_css_class("title-3")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        header.append(title)
        
        # Source badge
        self.source_badge = Gtk.Label()
        self.source_badge.add_css_class("pill")
        header.append(self.source_badge)
        
        self.append(header)
        
        # Mode selector row
        mode_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        mode_row.set_margin_top(8)
        mode_row.set_margin_start(12)
        mode_row.set_margin_end(12)
        
        mode_label = Gtk.Label(label="Mode")
        mode_label.set_halign(Gtk.Align.START)
        mode_label.set_hexpand(True)
        mode_row.append(mode_label)
        
        # Mode dropdown
        self.mode_dropdown = Gtk.DropDown()
        modes = Gtk.StringList.new(["Auto", "Local", "Remote"])
        self.mode_dropdown.set_model(modes)
        self.mode_dropdown.set_selected(0)  # Auto by default
        self.mode_dropdown.connect("notify::selected", self._on_mode_selected)
        mode_row.append(self.mode_dropdown)
        
        self.append(mode_row)
        
        # Remote configuration (collapsible)
        self.remote_config = Gtk.Revealer()
        self.remote_config.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        
        remote_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        remote_box.set_margin_top(8)
        remote_box.set_margin_start(12)
        remote_box.set_margin_end(12)
        
        # Host entry
        host_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        host_label = Gtk.Label(label="Remote Host")
        host_label.set_halign(Gtk.Align.START)
        host_label.set_hexpand(True)
        host_row.append(host_label)
        
        self.host_entry = Gtk.Entry()
        self.host_entry.set_text(self._remote_host)
        self.host_entry.set_placeholder_text("10.0.0.69")
        self.host_entry.connect("changed", self._on_host_changed)
        host_row.append(self.host_entry)
        remote_box.append(host_row)
        
        # Port entry
        port_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        port_label = Gtk.Label(label="Remote Port")
        port_label.set_halign(Gtk.Align.START)
        port_label.set_hexpand(True)
        port_row.append(port_label)
        
        self.port_entry = Gtk.Entry()
        self.port_entry.set_text(str(self._remote_port))
        self.port_entry.set_placeholder_text("8766")
        self.port_entry.connect("changed", self._on_port_changed)
        port_row.append(self.port_entry)
        remote_box.append(port_row)
        
        self.remote_config.set_child(remote_box)
        self.append(self.remote_config)
        
        # Status/error row
        self.status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_row.set_margin_top(8)
        self.status_row.set_margin_bottom(12)
        self.status_row.set_margin_start(12)
        self.status_row.set_margin_end(12)
        
        self.status_icon = Gtk.Image()
        self.status_icon.set_pixel_size(16)
        self.status_row.append(self.status_icon)
        
        self.status_label = Gtk.Label()
        self.status_label.add_css_class("dim-label")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_hexpand(True)
        self.status_label.set_wrap(True)
        self.status_row.append(self.status_label)
        
        self.append(self.status_row)
        
        # Load saved config
        self._load_config()
        
        # Initial state
        self._update_source_display()
    
    def _load_config(self):
        """Load saved configuration."""
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH) as f:
                    config = json.load(f)
                    self._current_mode = config.get("mode", "auto")
                    self._remote_host = config.get("remote_host", "10.0.0.69")
                    self._remote_port = config.get("remote_port", 8766)
                    
                    # Update UI
                    mode_map = {"auto": 0, "local": 1, "remote": 2}
                    self.mode_dropdown.set_selected(mode_map.get(self._current_mode, 0))
                    self.host_entry.set_text(self._remote_host)
                    self.port_entry.set_text(str(self._remote_port))
        except Exception as e:
            print(f"[ModeSwitcher] Config load error: {e}")
    
    def _save_config(self):
        """Save configuration to file."""
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            config = {
                "mode": self._current_mode,
                "remote_host": self._remote_host,
                "remote_port": self._remote_port
            }
            # Atomic write
            tmp_path = CONFIG_PATH.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(config, f, indent=2)
            tmp_path.rename(CONFIG_PATH)
        except Exception as e:
            print(f"[ModeSwitcher] Config save error: {e}")
    
    def _on_mode_selected(self, dropdown, param):
        """Handle mode dropdown selection."""
        selected = dropdown.get_selected()
        mode_map = {0: "auto", 1: "local", 2: "remote"}
        new_mode = mode_map.get(selected, "auto")
        
        if new_mode != self._current_mode:
            self._current_mode = new_mode
            self._save_config()
            
            # Show/hide remote config
            self.remote_config.set_reveal_child(new_mode == "remote")
            
            # Notify listener
            if self.on_mode_changed:
                self.on_mode_changed(new_mode)
    
    def _on_host_changed(self, entry):
        """Handle remote host change."""
        self._remote_host = entry.get_text()
        self._save_config()
    
    def _on_port_changed(self, entry):
        """Handle remote port change."""
        try:
            self._remote_port = int(entry.get_text())
            self._save_config()
        except ValueError:
            pass
    
    def get_config(self) -> dict:
        """Get current mode configuration."""
        return {
            "mode": self._current_mode,
            "remote_host": self._remote_host,
            "remote_port": self._remote_port
        }
    
    def update_from_daemon(self, data: dict):
        """Update display from daemon response."""
        self._current_source = data.get("source", "unknown")
        self._remote_error = data.get("remote_error")
        self._update_source_display()
    
    def _update_source_display(self):
        """Update source badge and status display."""
        # Source badge
        if self._current_source == "local":
            self.source_badge.set_text("LOCAL")
            self.source_badge.remove_css_class("warning")
            self.source_badge.remove_css_class("error")
            self.source_badge.add_css_class("success")
        elif self._current_source == "remote":
            self.source_badge.set_text("REMOTE")
            self.source_badge.remove_css_class("success")
            self.source_badge.remove_css_class("error")
            self.source_badge.add_css_class("accent")
        else:
            self.source_badge.set_text("UNKNOWN")
            self.source_badge.remove_css_class("success")
            self.source_badge.remove_css_class("accent")
        
        # Status/error
        if self._remote_error:
            self.status_icon.set_from_icon_name("dialog-warning-symbolic")
            self.status_label.set_text(f"Remote error: {self._remote_error}")
            self.status_label.add_css_class("error")
            self.status_row.set_visible(True)
        elif self._current_source == "remote":
            self.status_icon.set_from_icon_name("network-server-symbolic")
            self.status_label.set_text(f"Connected to {self._remote_host}:{self._remote_port}")
            self.status_label.remove_css_class("error")
            self.status_row.set_visible(True)
        elif self._current_source == "local":
            self.status_icon.set_from_icon_name("computer-symbolic")
            self.status_label.set_text("Monitoring local system")
            self.status_label.remove_css_class("error")
            self.status_row.set_visible(True)
        else:
            self.status_row.set_visible(False)
