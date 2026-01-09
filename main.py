#!/usr/bin/env python3
"""
Roxy Command Center - GTK4/Libadwaita Application
Production-grade AI workstation control panel.

SKOREQ Epic: ROXY-COMMAND-CENTER-GTK4-V1
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Gdk
import sys
import json
from pathlib import Path
from typing import Optional

# Import all components
from daemon_client import DaemonClient
from ui.header_bar import HeaderBar
from ui.navigation import MainNavigation
from ui.settings import SettingsPage
from widgets.overview_page import OverviewPage
from widgets.services_page import ServicesPage
from widgets.gpus_page import GpusPage
from widgets.ollama_panel import OllamaPanel
from widgets.alert_panel import AlertPanel
from widgets.terminal_pane import TerminalPage
from services.alert_manager import get_alert_manager

APP_ID = "org.roxy.CommandCenter"
CSS_PATH = Path(__file__).parent / "styles" / "custom.css"


class RoxyCommandCenter(Adw.Application):
    """Main application class."""
    
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self.window: Optional['MainWindow'] = None
    
    def do_startup(self):
        """Application startup."""
        Adw.Application.do_startup(self)
        
        # Load CSS
        self._load_css()
        
        # Set up actions
        self._setup_actions()
    
    def do_activate(self):
        """Application activation."""
        if not self.window:
            self.window = MainWindow(self)
        self.window.present()
    
    def _load_css(self):
        """Load custom CSS."""
        if not CSS_PATH.exists():
            print(f"[App] CSS not found: {CSS_PATH}")
            return
        
        try:
            css_provider = Gtk.CssProvider()
            css_provider.load_from_path(str(CSS_PATH))
            
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            print(f"[App] Loaded CSS from {CSS_PATH}")
        except Exception as e:
            print(f"[App] CSS load error: {e}")
    
    def _setup_actions(self):
        """Set up application actions."""
        # Quit action
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda a, p: self.quit())
        self.add_action(quit_action)
        
        # Keyboard shortcuts
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])


class MainWindow(Adw.ApplicationWindow):
    """Main application window."""
    
    def __init__(self, app: RoxyCommandCenter):
        super().__init__(application=app)
        self.app = app
        self.add_css_class("roxy-command-center")
        
        # Window properties
        self.set_title("Roxy Command Center")
        self.set_default_size(1280, 800)
        self.set_size_request(800, 600)
        
        # Data
        self._daemon_client = DaemonClient()
        self._current_data: dict = {}
        self._poll_source_id: Optional[int] = None
        
        # Initialize alert manager with app
        get_alert_manager(app)
        
        # Build UI
        self._build_ui()
        
        # Start polling
        self._start_polling()
    
    def _build_ui(self):
        """Build the main UI."""
        # Main vertical box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(main_box)
        
        # Header bar
        self.header = HeaderBar(
            on_settings=self._show_settings
        )
        main_box.append(self.header.get_widget())
        
        # Navigation + content
        self.navigation = MainNavigation()
        self.navigation.set_vexpand(True)
        main_box.append(self.navigation)
        
        # Add pages
        self._setup_pages()
        
        # Navigate to overview
        self.navigation.navigate_to("overview")
    
    def _setup_pages(self):
        """Set up navigation pages."""
        # Overview page
        self.overview_page = OverviewPage(
            on_navigate=self._on_navigate
        )
        self.navigation.add_page("overview", "Overview", self.overview_page, "view-grid-symbolic")
        
        # Services page
        self.services_page = ServicesPage()
        self.navigation.add_page("services", "Services", self.services_page, "system-run-symbolic")
        
        # GPUs page
        self.gpus_page = GpusPage()
        self.navigation.add_page("gpus", "GPUs", self.gpus_page, "video-display-symbolic")
        
        # Ollama page
        self.ollama_page = OllamaPanel()
        self.navigation.add_page("ollama", "Ollama", self.ollama_page, "face-smile-big-symbolic")
        
        # Alerts page
        self.alerts_page = AlertPanel()
        self.navigation.add_page("alerts", "Alerts", self.alerts_page, "dialog-warning-symbolic")
        
        # Terminal page
        self.terminal_page = TerminalPage()
        self.navigation.add_page("terminal", "Terminal", self.terminal_page, "utilities-terminal-symbolic")
        
        # Settings page
        self.settings_page = SettingsPage(
            on_setting_changed=self._on_setting_changed
        )
        self.navigation.add_page("settings", "Settings", self.settings_page, "emblem-system-symbolic")
    
    def _on_navigate(self, page_id: str):
        """Handle navigation from overview cards."""
        self.navigation.navigate_to(page_id)
    
    def _show_settings(self):
        """Show settings page."""
        self.navigation.navigate_to("settings")
    
    def _on_setting_changed(self, key: str, value):
        """Handle setting change."""
        print(f"[MainWindow] Setting changed: {key} = {value}")
        
        if key == "poll_interval_ms":
            self._restart_polling(int(value))
        elif key == "_reset":
            self._restart_polling()
    
    def _start_polling(self, interval_ms: int = 1000):
        """Start daemon polling."""
        self._stop_polling()
        
        # Initial fetch
        self._fetch_data()
        
        # Start periodic polling
        self._poll_source_id = GLib.timeout_add(interval_ms, self._on_poll_timer)
        print(f"[MainWindow] Started polling at {interval_ms}ms interval")
    
    def _stop_polling(self):
        """Stop daemon polling."""
        if self._poll_source_id:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None
    
    def _restart_polling(self, interval_ms: int = None):
        """Restart polling with new interval."""
        if interval_ms is None:
            config = self.settings_page.get_config()
            interval_ms = config.get("poll_interval_ms", 1000)
        self._start_polling(interval_ms)
    
    def _on_poll_timer(self) -> bool:
        """Periodic poll callback."""
        self._fetch_data()
        return True  # Continue
    
    def _fetch_data(self):
        """Fetch data from daemon."""
        def on_data(response):
            # Handle DaemonResponse object
            if hasattr(response, 'data'):
                data = response.data if response.data else {}
                if response.error:
                    data['error'] = response.error
            else:
                data = response if isinstance(response, dict) else {}
            
            if data:
                self._current_data = data
                self._update_ui(data)
                
                # Update header mode
                mode = data.get("mode", "local")
                host = data.get("remote_host", "")
                self.header.set_mode(mode, host)
                
                # Process alerts
                alert_manager = get_alert_manager()
                alert_manager.process_daemon_data(data)
                
                # Update alert badge in navigation
                alert_count = alert_manager.get_alert_count()
                self.navigation.set_badge("alerts", alert_count)
        
        self._daemon_client.fetch_async(on_data)
    
    def _update_ui(self, data: dict):
        """Update all UI components with new data."""
        # Overview
        self.overview_page.update(data)
        
        # Services
        self.services_page.update(data)
        
        # GPUs
        self.gpus_page.update(data)
        
        # Ollama
        self.ollama_page.update(data)
    
    def refresh(self):
        """Manual refresh."""
        self._fetch_data()
    
    def do_close_request(self) -> bool:
        """Handle window close."""
        self._stop_polling()
        return False  # Allow close


def main():
    """Application entry point."""
    app = RoxyCommandCenter()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
