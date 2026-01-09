#!/usr/bin/env python3
"""
Header bar with mode indicator, alert badge, and settings.
ROXY-CMD-STORY-008: Header bar with navigation.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Callable

from widgets.alert_panel import AlertBadge
from services.alert_manager import get_alert_manager


def create_header_bar(
    on_settings: Optional[Callable] = None,
    on_nav_back: Optional[Callable] = None
) -> Adw.HeaderBar:
    """
    Create application header bar.
    
    Features:
    - Mode indicator (LOCAL/REMOTE/AUTO)
    - Alert badge with count
    - Settings button
    - Title with subtitle showing mode
    """
    header = Adw.HeaderBar()
    
    # Title widget with mode indicator
    title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    title_box.set_valign(Gtk.Align.CENTER)
    
    title_label = Gtk.Label(label="Roxy Command Center")
    title_label.add_css_class("title")
    title_box.append(title_label)
    
    subtitle_label = Gtk.Label(label="LOCAL")
    subtitle_label.add_css_class("subtitle")
    subtitle_label.add_css_class("dim-label")
    title_box.append(subtitle_label)
    
    header.set_title_widget(title_box)
    
    # Left side - mode badge
    mode_badge = Gtk.Label(label="LOCAL")
    mode_badge.add_css_class("mode-badge")
    mode_badge.add_css_class("mode-local")
    mode_badge.set_margin_start(4)
    mode_badge.set_margin_end(4)
    header.pack_start(mode_badge)
    
    # Right side - alert badge
    alert_badge = AlertBadge()
    header.pack_end(alert_badge)
    
    # Settings button
    settings_btn = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
    settings_btn.set_tooltip_text("Settings")
    if on_settings:
        settings_btn.connect("clicked", lambda b: on_settings())
    header.pack_end(settings_btn)
    
    # Refresh button
    refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
    refresh_btn.set_tooltip_text("Refresh")
    header.pack_end(refresh_btn)
    
    # Store references for updating
    header._mode_badge = mode_badge
    header._subtitle_label = subtitle_label
    header._alert_badge = alert_badge
    header._refresh_btn = refresh_btn
    
    return header


class HeaderBar:
    """
    Wrapper class for header bar management.
    
    Features:
    - Mode indicator (LOCAL/REMOTE/AUTO)
    - Alert badge with count
    - Settings button
    - Title with subtitle showing mode
    """
    
    def __init__(
        self,
        on_settings: Optional[Callable] = None,
        on_nav_back: Optional[Callable] = None
    ):
        self.on_settings = on_settings
        self.on_nav_back = on_nav_back
        
        self._current_mode = "local"
        self._remote_host = ""
        
        self._widget = Adw.HeaderBar()
        self._build_ui()
    
    def _build_ui(self):
        # Title widget with mode indicator
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_valign(Gtk.Align.CENTER)
        
        self.title_label = Gtk.Label(label="Roxy Command Center")
        self.title_label.add_css_class("title")
        title_box.append(self.title_label)
        
        self.subtitle_label = Gtk.Label(label="LOCAL")
        self.subtitle_label.add_css_class("subtitle")
        self.subtitle_label.add_css_class("dim-label")
        title_box.append(self.subtitle_label)
        
        self._widget.set_title_widget(title_box)
        
        # Left side - mode badge
        self.mode_badge = Gtk.Label(label="LOCAL")
        self.mode_badge.add_css_class("mode-badge")
        self.mode_badge.add_css_class("mode-local")
        self.mode_badge.set_margin_start(4)
        self.mode_badge.set_margin_end(4)
        self._widget.pack_start(self.mode_badge)
        
        # Right side - alert badge
        self.alert_badge = AlertBadge()
        self._widget.pack_end(self.alert_badge)
        
        # Settings button
        settings_btn = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.connect("clicked", self._on_settings_clicked)
        self._widget.pack_end(settings_btn)
        
        # Refresh button
        self.refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text("Refresh")
        self.refresh_btn.connect("clicked", self._on_refresh_clicked)
        self._widget.pack_end(self.refresh_btn)
        
        # Sleep button - graceful system sleep
        self.sleep_btn = Gtk.Button.new_from_icon_name("weather-clear-night-symbolic")
        self.sleep_btn.set_tooltip_text("Sleep System (gracefully stops services)")
        self.sleep_btn.connect("clicked", self._on_sleep_clicked)
        self._widget.pack_start(self.sleep_btn)
    
    def get_widget(self) -> Adw.HeaderBar:
        """Get the underlying GTK widget."""
        return self._widget
    
    def set_mode(self, mode: str, host: str = ""):
        """Update mode display (local/remote/auto)."""
        self._current_mode = mode.lower()
        self._remote_host = host
        
        # Remove old mode classes
        self.mode_badge.remove_css_class("mode-local")
        self.mode_badge.remove_css_class("mode-remote")
        self.mode_badge.remove_css_class("mode-auto")
        
        if self._current_mode == "remote":
            self.mode_badge.set_label("REMOTE")
            self.mode_badge.add_css_class("mode-remote")
            self.subtitle_label.set_label(f"REMOTE → {host}" if host else "REMOTE")
        elif self._current_mode == "auto":
            self.mode_badge.set_label("AUTO")
            self.mode_badge.add_css_class("mode-auto")
            self.subtitle_label.set_label("AUTO")
        else:
            self.mode_badge.set_label("LOCAL")
            self.mode_badge.add_css_class("mode-local")
            self.subtitle_label.set_label("LOCAL")
    
    def set_subtitle(self, text: str):
        """Set custom subtitle text."""
        self.subtitle_label.set_label(text)
    
    def _on_settings_clicked(self, button):
        if self.on_settings:
            self.on_settings()
    
    def _on_refresh_clicked(self, button):
        """Emit refresh signal to parent."""
        # Spin the icon briefly
        button.set_sensitive(False)
        GLib.timeout_add(500, lambda: button.set_sensitive(True) or False)
        
        # Get the window and call refresh if available
        window = self._widget.get_root()
        if window and hasattr(window, 'refresh'):
            window.refresh()
    
    def _on_sleep_clicked(self, button):
        """Handle sleep button - show confirmation dialog."""
        window = self._widget.get_root()
        if not isinstance(window, Gtk.Window):
            return
        
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Sleep System?",
            body="This will gracefully stop Ollama services and put the system to sleep. GPUs will cool down safely."
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("sleep", "Sleep Now")
        dialog.set_response_appearance("sleep", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        
        dialog.connect("response", self._on_sleep_response)
        dialog.present()
    
    def _on_sleep_response(self, dialog, response):
        """Handle sleep dialog response."""
        if response != "sleep":
            return
        
        # Get window for status updates
        window = self._widget.get_root()
        
        # Perform graceful shutdown sequence
        import subprocess
        import threading
        
        def do_sleep():
            try:
                # Step 1: Stop Ollama services gracefully
                subprocess.run(
                    ["systemctl", "--user", "stop", "ollama-big.service"],
                    timeout=10, capture_output=True
                )
                subprocess.run(
                    ["systemctl", "--user", "stop", "ollama-fast.service"],
                    timeout=10, capture_output=True
                )
                
                # Step 2: Let GPUs cool down briefly
                import time
                time.sleep(2)
                
                # Step 3: Initiate system sleep
                subprocess.run(
                    ["systemctl", "suspend"],
                    timeout=10, capture_output=True
                )
            except Exception as e:
                print(f"[Sleep] Error: {e}")
                GLib.idle_add(lambda: self._show_sleep_error(str(e)))
        
        # Run in thread to not block UI
        thread = threading.Thread(target=do_sleep, daemon=True)
        thread.start()
        
        # Update button to show in progress
        self.sleep_btn.set_sensitive(False)
        self.sleep_btn.set_tooltip_text("Sleeping...")
        GLib.timeout_add(15000, lambda: self._reset_sleep_button() or False)
    
    def _reset_sleep_button(self):
        """Reset sleep button after timeout (in case sleep was cancelled)."""
        self.sleep_btn.set_sensitive(True)
        self.sleep_btn.set_tooltip_text("Sleep System (gracefully stops services)")
    
    def _show_sleep_error(self, error: str):
        """Show sleep error dialog."""
        window = self._widget.get_root()
        if not isinstance(window, Gtk.Window):
            return
        
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Sleep Failed",
            body=f"Could not put system to sleep: {error}"
        )
        dialog.add_response("ok", "OK")
        dialog.present()
        self._reset_sleep_button()


class MiniModeIndicator(Gtk.Box):
    """
    Small mode indicator for compact spaces.
    Shows colored dot + mode text.
    """
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.add_css_class("mini-mode-indicator")
        
        self.dot = Gtk.Label(label="●")
        self.dot.add_css_class("mode-dot")
        self.dot.add_css_class("mode-local")
        self.append(self.dot)
        
        self.label = Gtk.Label(label="Local")
        self.label.add_css_class("caption")
        self.append(self.label)
    
    def set_mode(self, mode: str, host: str = ""):
        """Update mode display."""
        self.dot.remove_css_class("mode-local")
        self.dot.remove_css_class("mode-remote")
        self.dot.remove_css_class("mode-auto")
        
        mode = mode.lower()
        if mode == "remote":
            self.dot.add_css_class("mode-remote")
            self.label.set_label(f"Remote: {host}" if host else "Remote")
        elif mode == "auto":
            self.dot.add_css_class("mode-auto")
            self.label.set_label("Auto")
        else:
            self.dot.add_css_class("mode-local")
            self.label.set_label("Local")


class ConnectionStatus(Gtk.Box):
    """
    Connection status indicator.
    Shows whether we're connected to daemon/remote.
    """
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.add_css_class("connection-status")
        
        self.icon = Gtk.Image.new_from_icon_name("network-offline-symbolic")
        self.icon.set_pixel_size(16)
        self.append(self.icon)
        
        self.label = Gtk.Label(label="Connecting...")
        self.label.add_css_class("caption")
        self.append(self.label)
        
        self._is_connected = False
    
    def set_connected(self, connected: bool, latency_ms: int = 0):
        """Update connection status."""
        self._is_connected = connected
        
        self.remove_css_class("connected")
        self.remove_css_class("disconnected")
        
        if connected:
            self.add_css_class("connected")
            self.icon.set_from_icon_name("network-transmit-receive-symbolic")
            if latency_ms > 0:
                self.label.set_label(f"Connected ({latency_ms}ms)")
            else:
                self.label.set_label("Connected")
        else:
            self.add_css_class("disconnected")
            self.icon.set_from_icon_name("network-offline-symbolic")
            self.label.set_label("Disconnected")
    
    def set_error(self, error_msg: str):
        """Show error status."""
        self.remove_css_class("connected")
        self.add_css_class("disconnected")
        self.icon.set_from_icon_name("dialog-error-symbolic")
        self.label.set_label(error_msg)
