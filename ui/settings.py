#!/usr/bin/env python3
"""
Settings page with configuration options.
ROXY-CMD-STORY-021: Settings and configuration.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
import json
from pathlib import Path
from typing import Optional, Callable

from services.alert_manager import get_alert_manager, AlertType

CONFIG_PATH = Path.home() / ".config/roxy-command-center/config.json"


class SettingsPage(Gtk.ScrolledWindow):
    """
    Settings page with configuration options.
    
    Features:
    - Mode configuration
    - Alert thresholds
    - Notification settings
    - UI preferences
    """
    
    def __init__(self, on_setting_changed: Optional[Callable[[str, any], None]] = None):
        super().__init__()
        self.on_setting_changed = on_setting_changed
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self._config = self._load_config()
        self._build_ui()
    
    def _load_config(self) -> dict:
        """Load configuration."""
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH) as f:
                    return json.load(f)
        except Exception as e:
            print(f"[Settings] Config load error: {e}")
        
        return {
            "mode": "local",
            "remote_host": "",
            "remote_port": 8080,
            "poll_interval_ms": 1000,
            "notifications_enabled": True,
            "theme": "system",
            "show_graphs": True,
            "gpu_temp_warning": 70,
            "gpu_temp_critical": 80,
            "vram_warning": 80,
            "vram_critical": 95,
        }
    
    def _save_config(self):
        """Save configuration."""
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = CONFIG_PATH.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(self._config, f, indent=2)
            tmp_path.rename(CONFIG_PATH)
        except Exception as e:
            print(f"[Settings] Config save error: {e}")
    
    def _emit_change(self, key: str, value):
        """Emit setting change."""
        self._config[key] = value
        self._save_config()
        
        if self.on_setting_changed:
            self.on_setting_changed(key, value)
    
    def _build_ui(self):
        # Main container with max width
        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_tightening_threshold(400)
        self.set_child(clamp)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(12)
        main_box.set_margin_end(12)
        clamp.set_child(main_box)
        
        # Connection Settings
        conn_group = Adw.PreferencesGroup()
        conn_group.set_title("Connection")
        conn_group.set_description("Configure data source mode")
        main_box.append(conn_group)
        
        # Mode selector
        mode_row = Adw.ComboRow()
        mode_row.set_title("Mode")
        mode_row.set_subtitle("How to fetch system data")
        
        mode_model = Gtk.StringList()
        for mode in ["Local (daemon)", "Remote (HTTP)", "Auto"]:
            mode_model.append(mode)
        mode_row.set_model(mode_model)
        
        current_mode = self._config.get("mode", "local")
        mode_index = {"local": 0, "remote": 1, "auto": 2}.get(current_mode, 0)
        mode_row.set_selected(mode_index)
        mode_row.connect("notify::selected", self._on_mode_changed)
        conn_group.add(mode_row)
        
        # Remote host
        self.host_row = Adw.EntryRow()
        self.host_row.set_title("Remote Host")
        self.host_row.set_text(self._config.get("remote_host", ""))
        self.host_row.connect("changed", self._on_host_changed)
        self.host_row.set_sensitive(current_mode == "remote")
        conn_group.add(self.host_row)
        
        # Remote port
        self.port_row = Adw.SpinRow.new_with_range(1, 65535, 1)
        self.port_row.set_title("Remote Port")
        self.port_row.set_value(self._config.get("remote_port", 8080))
        self.port_row.connect("notify::value", self._on_port_changed)
        self.port_row.set_sensitive(current_mode == "remote")
        conn_group.add(self.port_row)
        
        # Poll interval
        poll_row = Adw.SpinRow.new_with_range(500, 10000, 100)
        poll_row.set_title("Poll Interval (ms)")
        poll_row.set_subtitle("How often to fetch data")
        poll_row.set_value(self._config.get("poll_interval_ms", 1000))
        poll_row.connect("notify::value", self._on_poll_interval_changed)
        conn_group.add(poll_row)
        
        # Alert Settings
        alert_group = Adw.PreferencesGroup()
        alert_group.set_title("Alerts")
        alert_group.set_description("Configure alert thresholds")
        main_box.append(alert_group)
        
        # Notifications toggle
        notif_row = Adw.SwitchRow()
        notif_row.set_title("Desktop Notifications")
        notif_row.set_subtitle("Show system notifications for alerts")
        notif_row.set_active(self._config.get("notifications_enabled", True))
        notif_row.connect("notify::active", self._on_notifications_changed)
        alert_group.add(notif_row)
        
        # GPU temperature warning
        gpu_warn_row = Adw.SpinRow.new_with_range(50, 100, 5)
        gpu_warn_row.set_title("GPU Temp Warning (°C)")
        gpu_warn_row.set_value(self._config.get("gpu_temp_warning", 70))
        gpu_warn_row.connect("notify::value", lambda r, p: self._on_threshold_changed("gpu_temp_warning", r.get_value()))
        alert_group.add(gpu_warn_row)
        
        # GPU temperature critical
        gpu_crit_row = Adw.SpinRow.new_with_range(60, 110, 5)
        gpu_crit_row.set_title("GPU Temp Critical (°C)")
        gpu_crit_row.set_value(self._config.get("gpu_temp_critical", 80))
        gpu_crit_row.connect("notify::value", lambda r, p: self._on_threshold_changed("gpu_temp_critical", r.get_value()))
        alert_group.add(gpu_crit_row)
        
        # VRAM warning
        vram_warn_row = Adw.SpinRow.new_with_range(50, 100, 5)
        vram_warn_row.set_title("VRAM Warning (%)")
        vram_warn_row.set_value(self._config.get("vram_warning", 80))
        vram_warn_row.connect("notify::value", lambda r, p: self._on_threshold_changed("vram_warning", r.get_value()))
        alert_group.add(vram_warn_row)
        
        # VRAM critical
        vram_crit_row = Adw.SpinRow.new_with_range(70, 100, 5)
        vram_crit_row.set_title("VRAM Critical (%)")
        vram_crit_row.set_value(self._config.get("vram_critical", 95))
        vram_crit_row.connect("notify::value", lambda r, p: self._on_threshold_changed("vram_critical", r.get_value()))
        alert_group.add(vram_crit_row)
        
        # Appearance Settings
        appear_group = Adw.PreferencesGroup()
        appear_group.set_title("Appearance")
        main_box.append(appear_group)
        
        # Theme
        theme_row = Adw.ComboRow()
        theme_row.set_title("Theme")
        
        theme_model = Gtk.StringList()
        for theme in ["System", "Light", "Dark"]:
            theme_model.append(theme)
        theme_row.set_model(theme_model)
        
        current_theme = self._config.get("theme", "system")
        theme_index = {"system": 0, "light": 1, "dark": 2}.get(current_theme, 0)
        theme_row.set_selected(theme_index)
        theme_row.connect("notify::selected", self._on_theme_changed)
        appear_group.add(theme_row)
        
        # Show graphs
        graphs_row = Adw.SwitchRow()
        graphs_row.set_title("Show Graphs")
        graphs_row.set_subtitle("Display history graphs in overview")
        graphs_row.set_active(self._config.get("show_graphs", True))
        graphs_row.connect("notify::active", self._on_graphs_changed)
        appear_group.add(graphs_row)
        
        # About Section
        about_group = Adw.PreferencesGroup()
        about_group.set_title("About")
        main_box.append(about_group)
        
        # Version info
        version_row = Adw.ActionRow()
        version_row.set_title("Version")
        version_row.set_subtitle("1.0.0")
        about_group.add(version_row)
        
        # GitHub link
        github_row = Adw.ActionRow()
        github_row.set_title("Source Code")
        github_row.set_subtitle("Roxy Command Center GTK4")
        github_row.set_activatable(True)
        github_row.add_suffix(Gtk.Image.new_from_icon_name("external-link-symbolic"))
        about_group.add(github_row)
        
        # Reset button
        reset_row = Adw.ActionRow()
        reset_row.set_title("Reset Settings")
        reset_row.set_subtitle("Restore all settings to defaults")
        
        reset_btn = Gtk.Button(label="Reset")
        reset_btn.add_css_class("destructive-action")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_reset_clicked)
        reset_row.add_suffix(reset_btn)
        about_group.add(reset_row)
    
    def _on_mode_changed(self, row, pspec):
        """Handle mode change."""
        modes = ["local", "remote", "auto"]
        mode = modes[row.get_selected()]
        
        self.host_row.set_sensitive(mode == "remote")
        self.port_row.set_sensitive(mode == "remote")
        
        self._emit_change("mode", mode)
    
    def _on_host_changed(self, row):
        """Handle remote host change."""
        self._emit_change("remote_host", row.get_text())
    
    def _on_port_changed(self, row, pspec):
        """Handle remote port change."""
        self._emit_change("remote_port", int(row.get_value()))
    
    def _on_poll_interval_changed(self, row, pspec):
        """Handle poll interval change."""
        self._emit_change("poll_interval_ms", int(row.get_value()))
    
    def _on_notifications_changed(self, row, pspec):
        """Handle notifications toggle."""
        enabled = row.get_active()
        self._emit_change("notifications_enabled", enabled)
        
        # Update alert manager
        alert_manager = get_alert_manager()
        alert_manager.notifications_enabled = enabled
        alert_manager.save_config()
    
    def _on_threshold_changed(self, key: str, value: float):
        """Handle threshold change."""
        self._emit_change(key, int(value))
        
        # Update alert manager
        alert_manager = get_alert_manager()
        
        if key == "gpu_temp_warning":
            alert_manager.thresholds[AlertType.GPU_TEMP].warning_threshold = value
        elif key == "gpu_temp_critical":
            alert_manager.thresholds[AlertType.GPU_TEMP].critical_threshold = value
        elif key == "vram_warning":
            alert_manager.thresholds[AlertType.GPU_VRAM].warning_threshold = value
        elif key == "vram_critical":
            alert_manager.thresholds[AlertType.GPU_VRAM].critical_threshold = value
        
        alert_manager.save_config()
    
    def _on_theme_changed(self, row, pspec):
        """Handle theme change."""
        themes = ["system", "light", "dark"]
        theme = themes[row.get_selected()]
        self._emit_change("theme", theme)
        
        # Apply theme
        style_manager = Adw.StyleManager.get_default()
        if theme == "light":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        elif theme == "dark":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
    
    def _on_graphs_changed(self, row, pspec):
        """Handle graphs toggle."""
        self._emit_change("show_graphs", row.get_active())
    
    def _on_reset_clicked(self, button):
        """Reset all settings to defaults."""
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            "Reset Settings?",
            "This will restore all settings to their default values."
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_reset_response)
        dialog.present()
    
    def _on_reset_response(self, dialog, response):
        """Handle reset dialog response."""
        if response == "reset":
            # Delete config file
            try:
                if CONFIG_PATH.exists():
                    CONFIG_PATH.unlink()
            except Exception as e:
                print(f"[Settings] Reset error: {e}")
            
            # Reload defaults
            self._config = self._load_config()
            
            # Notify parent
            if self.on_setting_changed:
                self.on_setting_changed("_reset", True)
    
    def get_config(self) -> dict:
        """Get current configuration."""
        return dict(self._config)
