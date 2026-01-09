#!/usr/bin/env python3
"""
Service card widget with status indicators and action buttons.
ROXY-CMD-STORY-002 & ROXY-CMD-STORY-004: Service display and control.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
from typing import Optional, Callable
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.systemd_control import get_systemd, ServiceAction, ActionResult

class ServiceCard(Gtk.Box):
    """
    Service status card with action buttons.
    
    Shows:
    - Service name and port
    - Status icon (running/stopped/error)
    - Health indicator
    - Start/Stop/Restart buttons with confirmation
    """
    
    def __init__(self, 
                 service_name: str,
                 display_name: str,
                 port: Optional[int] = None,
                 on_action: Optional[Callable[[str, str], None]] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        self.service_name = service_name
        self.display_name = display_name
        self.port = port
        self.on_action = on_action
        self._cooldown_timer: Optional[int] = None
        
        # Card styling
        self.add_css_class("card")
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        
        # Header row
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_margin_top(12)
        header.set_margin_start(12)
        header.set_margin_end(12)
        
        # Status icon
        self.status_icon = Gtk.Image()
        self.status_icon.set_pixel_size(24)
        header.append(self.status_icon)
        
        # Name and port
        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name_box.set_hexpand(True)
        
        self.name_label = Gtk.Label(label=display_name)
        self.name_label.add_css_class("title-3")
        self.name_label.set_halign(Gtk.Align.START)
        name_box.append(self.name_label)
        
        if port:
            self.port_label = Gtk.Label(label=f"Port {port}")
            self.port_label.add_css_class("dim-label")
            self.port_label.set_halign(Gtk.Align.START)
            name_box.append(self.port_label)
        
        header.append(name_box)
        
        # Health badge
        self.health_badge = Gtk.Label()
        self.health_badge.add_css_class("pill")
        header.append(self.health_badge)
        
        self.append(header)
        
        # Status row
        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_row.set_margin_start(12)
        status_row.set_margin_end(12)
        
        self.status_label = Gtk.Label(label="Unknown")
        self.status_label.add_css_class("dim-label")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_hexpand(True)
        status_row.append(self.status_label)
        
        self.append(status_row)
        
        # Action buttons row
        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_row.set_margin_top(8)
        button_row.set_margin_bottom(12)
        button_row.set_margin_start(12)
        button_row.set_margin_end(12)
        button_row.set_halign(Gtk.Align.END)
        
        self.start_button = Gtk.Button(label="Start")
        self.start_button.add_css_class("suggested-action")
        self.start_button.connect("clicked", self._on_start_clicked)
        button_row.append(self.start_button)
        
        self.stop_button = Gtk.Button(label="Stop")
        self.stop_button.add_css_class("destructive-action")
        self.stop_button.connect("clicked", self._on_stop_clicked)
        button_row.append(self.stop_button)
        
        self.restart_button = Gtk.Button(label="Restart")
        self.restart_button.connect("clicked", self._on_restart_clicked)
        button_row.append(self.restart_button)
        
        self.append(button_row)
        
        # Cooldown indicator
        self.cooldown_label = Gtk.Label()
        self.cooldown_label.add_css_class("dim-label")
        self.cooldown_label.set_margin_bottom(8)
        self.cooldown_label.set_visible(False)
        self.append(self.cooldown_label)
        
        # Spinner for loading state
        self.spinner = Gtk.Spinner()
        self.spinner.set_visible(False)
        
        # Initial state
        self.set_status("unknown", "unknown")
    
    def set_status(self, status: str, health: str = "unknown"):
        """
        Update service status display.
        
        status: "running", "stopped", "error", "unknown"
        health: "healthy", "degraded", "unhealthy", "unknown"
        """
        # Status icon
        if status == "running" or status == "active":
            self.status_icon.set_from_icon_name("emblem-ok-symbolic")
            self.status_icon.add_css_class("success")
            self.status_label.set_text("Running")
            self.start_button.set_sensitive(False)
            self.stop_button.set_sensitive(True)
            self.restart_button.set_sensitive(True)
        elif status == "stopped" or status == "inactive" or status == "dead":
            self.status_icon.set_from_icon_name("media-playback-stop-symbolic")
            self.status_icon.remove_css_class("success")
            self.status_icon.remove_css_class("error")
            self.status_label.set_text("Stopped")
            self.start_button.set_sensitive(True)
            self.stop_button.set_sensitive(False)
            self.restart_button.set_sensitive(False)
        elif status == "error" or status == "failed":
            self.status_icon.set_from_icon_name("dialog-error-symbolic")
            self.status_icon.add_css_class("error")
            self.status_label.set_text("Error")
            self.start_button.set_sensitive(True)
            self.stop_button.set_sensitive(True)
            self.restart_button.set_sensitive(True)
        else:
            self.status_icon.set_from_icon_name("dialog-question-symbolic")
            self.status_label.set_text(status.title() if status else "Unknown")
        
        # Health badge
        if health == "healthy" or health == "ok":
            self.health_badge.set_text("Healthy")
            self.health_badge.remove_css_class("warning")
            self.health_badge.remove_css_class("error")
            self.health_badge.add_css_class("success")
        elif health == "degraded":
            self.health_badge.set_text("Degraded")
            self.health_badge.remove_css_class("success")
            self.health_badge.remove_css_class("error")
            self.health_badge.add_css_class("warning")
        elif health == "unhealthy" or health == "error":
            self.health_badge.set_text("Unhealthy")
            self.health_badge.remove_css_class("success")
            self.health_badge.remove_css_class("warning")
            self.health_badge.add_css_class("error")
        else:
            self.health_badge.set_text("")
    
    def update_from_daemon(self, service_data: dict):
        """Update from daemon JSON data."""
        if not service_data:
            self.set_status("unknown", "unknown")
            return
        
        # Map daemon health to status
        health = service_data.get("health", "unknown")
        if health == "ok":
            self.set_status("running", "healthy")
        elif health == "unhealthy":
            self.set_status("error", "unhealthy")
        elif health == "degraded":
            self.set_status("running", "degraded")
        else:
            self.set_status("unknown", "unknown")
    
    def update(self, service_data: dict):
        """Update card with service data from daemon."""
        # Get status info
        active = service_data.get("active", False)
        health = service_data.get("health", "unknown")
        port_open = service_data.get("port_open", False)
        models = service_data.get("models_loaded", [])
        vram = service_data.get("vram_used_gb", 0)
        
        # Determine status
        if active:
            if health in ("ok", "healthy"):
                self.set_status("running", "healthy")
            else:
                self.set_status("running", health)
        else:
            self.set_status("stopped", "stopped")
        
        # Update port info
        if self.port and hasattr(self, 'port_label'):
            port_status = "✓" if port_open else "✗"
            self.port_label.set_text(f":{self.port} {port_status}")
        
        # Update models if this is an Ollama service
        if models and hasattr(self, 'models_label'):
            self.models_label.set_text(f"{len(models)} models, {vram:.1f}GB")
            self.models_label.set_visible(True)
    
    def get_status(self) -> str:
        """Get current status string."""
        return self._current_status if hasattr(self, '_current_status') else "unknown"
    
    def get_health(self) -> str:
        """Get current health string."""
        return self._current_health if hasattr(self, '_current_health') else "unknown"
    
    def _check_cooldown(self) -> bool:
        """Check if on cooldown, update UI if so."""
        systemd = get_systemd()
        if systemd.is_on_cooldown(self.service_name):
            remaining = systemd.get_cooldown_remaining(self.service_name)
            self.cooldown_label.set_text(f"Cooldown: {remaining:.0f}s")
            self.cooldown_label.set_visible(True)
            self._disable_buttons()
            return True
        else:
            self.cooldown_label.set_visible(False)
            return False
    
    def _disable_buttons(self):
        """Disable all action buttons."""
        self.start_button.set_sensitive(False)
        self.stop_button.set_sensitive(False)
        self.restart_button.set_sensitive(False)
    
    def _start_cooldown_timer(self):
        """Start timer to re-enable buttons after cooldown."""
        if self._cooldown_timer:
            GLib.source_remove(self._cooldown_timer)
        
        def update_cooldown():
            if self._check_cooldown():
                return True  # Continue timer
            else:
                self._cooldown_timer = None
                # Refresh status to enable appropriate buttons
                self._refresh_status()
                return False  # Stop timer
        
        self._cooldown_timer = GLib.timeout_add(500, update_cooldown)
    
    def _refresh_status(self):
        """Refresh service status from systemd."""
        systemd = get_systemd()
        active, sub = systemd.get_service_state(self.service_name)
        self.set_status(active, "healthy" if active == "active" else "unknown")
    
    def _show_confirmation(self, action: str, callback: Callable):
        """Show confirmation dialog before action."""
        window = self.get_root()
        if not isinstance(window, Gtk.Window):
            callback()
            return
        
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading=f"{action.title()} Service?",
            body=f"Are you sure you want to {action} {self.display_name}?"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("confirm", action.title())
        dialog.set_response_appearance("confirm", 
            Adw.ResponseAppearance.DESTRUCTIVE if action == "stop" else Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        
        def on_response(d, response):
            if response == "confirm":
                callback()
        
        dialog.connect("response", on_response)
        dialog.present()
    
    def _on_action_complete(self, result: ServiceAction):
        """Handle action completion."""
        # Show toast
        window = self.get_root()
        if isinstance(window, Adw.ApplicationWindow):
            toast = Adw.Toast(title=f"{result.action.title()}: {result.message}")
            if result.result == ActionResult.SUCCESS:
                toast.set_timeout(2)
            else:
                toast.set_timeout(5)
            # Find toast overlay
            # toast_overlay.add_toast(toast)
        
        # Refresh status
        if result.new_state:
            state = result.new_state.split()[0] if result.new_state else "unknown"
            self.set_status(state)
        
        # Start cooldown timer
        self._start_cooldown_timer()
        
        # Callback
        if self.on_action:
            self.on_action(self.service_name, result.action)
    
    def _on_start_clicked(self, button):
        """Handle start button click."""
        if self._check_cooldown():
            return
        
        def do_start():
            self._disable_buttons()
            self.status_label.set_text("Starting...")
            systemd = get_systemd()
            systemd.start_service(self.service_name, self._on_action_complete)
        
        self._show_confirmation("start", do_start)
    
    def _on_stop_clicked(self, button):
        """Handle stop button click."""
        if self._check_cooldown():
            return
        
        def do_stop():
            self._disable_buttons()
            self.status_label.set_text("Stopping...")
            systemd = get_systemd()
            systemd.stop_service(self.service_name, self._on_action_complete)
        
        self._show_confirmation("stop", do_stop)
    
    def _on_restart_clicked(self, button):
        """Handle restart button click."""
        if self._check_cooldown():
            return
        
        def do_restart():
            self._disable_buttons()
            self.status_label.set_text("Restarting...")
            systemd = get_systemd()
            systemd.restart_service(self.service_name, self._on_action_complete)
        
        self._show_confirmation("restart", do_restart)
