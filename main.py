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
import os
import json
import signal
import faulthandler
from pathlib import Path
from typing import Optional, List
from datetime import datetime

# Import all components
from daemon_client import DaemonClient, normalize_status
from ui.header_bar import HeaderBar
from ui.navigation import MainNavigation
from ui.settings import SettingsPage
from widgets.home_console_page import HomeConsolePage
from widgets.overview_page import OverviewPage
from widgets.services_page import ServicesPage
from widgets.gpus_page import GpusPage
from widgets.roxy_status_page import RoxyStatusPage
from widgets.mos_cockpit_page import MOSCockpitPage
from widgets.ollama_panel import OllamaPanel
from widgets.alert_panel import AlertPanel
from widgets.terminal_pane import TerminalPage
from services.alert_manager import get_alert_manager
from services.ollama_control import get_ollama_control, OllamaAction, ActionResult

APP_ID = "org.roxy.CommandCenter.Phase2CReview"
CSS_PATH = Path(__file__).parent / "styles" / "custom.css"


class RoxyCommandCenter(Adw.Application):
    """Main application class."""
    
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self.window: Optional['MainWindow'] = None
        self._signal_handler_ids: List[int] = []
        self._fault_log = self._setup_fault_logging()
    
    def do_startup(self):
        """Application startup."""
        print("[App] ========== STARTUP BEGIN ==========")
        print(f"[App] PID: {os.getpid()}")
        
        # Check for unexpected death from previous run
        self._check_previous_exit()
        
        Adw.Application.do_startup(self)
        print("[App] Setting up signal handlers...")
        self._setup_signal_handlers()
        print("[App] Signal handlers registered")
        
        # Load CSS
        print("[App] Loading CSS...")
        self._load_css()
        
        # Set up actions
        print("[App] Setting up actions...")
        self._setup_actions()
        print("[App] ========== STARTUP COMPLETE ==========")
    
    def do_activate(self):
        """Application activation."""
        print("[App] ========== ACTIVATE BEGIN ==========")
        if not self.window:
            print("[App] Creating main window...")
            self.window = MainWindow(self)
            print("[App] Main window created")
        print("[App] Presenting window...")
        self.window.present()
        print("[App] ========== ACTIVATE COMPLETE ==========")

    def do_shutdown(self):
        """Application shutdown."""
        print(f"[App] Shutting down (PID {os.getpid()})")
        self._write_exit_breadcrumb("user_close", "Normal shutdown")
        
        for handler_id in list(self._signal_handler_ids):
            try:
                GLib.source_remove(handler_id)
            except Exception:
                pass
        self._signal_handler_ids.clear()
        if self._fault_log:
            try:
                faulthandler.disable()
            except Exception:
                pass
            try:
                self._fault_log.close()
            except Exception:
                pass
        Adw.Application.do_shutdown(self)

    def _setup_fault_logging(self):
        """Register faulthandler to capture stack traces on termination."""
        try:
            log_dir = Path.home() / ".cache" / "roxy-command-center"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "fault.log"
            log_file = log_path.open("a", buffering=1)
            faulthandler.enable(file=log_file)
            for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR1, signal.SIGUSR2):
                try:
                    faulthandler.register(sig, log_file, all_threads=True)
                except (RuntimeError, ValueError):
                    pass
            return log_file
        except Exception as exc:
            print(f"[App] Fault logging setup failed: {exc}")
            return None

    def _setup_signal_handlers(self):
        """Register signal handlers so unexpected terminations are logged."""
        def _handle_signal(sig: int) -> bool:
            try:
                name = signal.Signals(sig).name
            except Exception:
                name = str(sig)
            print(f"[App] Received signal {sig} ({name}); initiating graceful shutdown")
            self._write_exit_breadcrumb(f"signal:{name}", f"Terminated by signal {sig}")
            self._signal_handler_ids.clear()
            GLib.idle_add(self.quit)
            return False  # Remove handler after first invocation

        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            try:
                handler_id = GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda sig=sig: _handle_signal(sig))
                self._signal_handler_ids.append(handler_id)
            except Exception as exc:
                print(f"[App] Failed to register handler for signal {sig}: {exc}")
    
    def _write_exit_breadcrumb(self, reason: str, details: str = ""):
        """Write exit breadcrumb for crash classification."""
        try:
            cache_dir = Path.home() / ".cache" / "roxy-command-center"
            cache_dir.mkdir(parents=True, exist_ok=True)
            breadcrumb_path = cache_dir / "last_exit.json"
            
            data = {
                "ts": datetime.now().isoformat(),
                "pid": os.getpid(),
                "reason": reason,
                "details": details
            }
            
            with open(breadcrumb_path, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(f"[App] Warning: Could not write exit breadcrumb: {e}")
    
    def _check_previous_exit(self):
        """Check for unexpected death from previous run."""
        try:
            breadcrumb_path = Path.home() / ".cache" / "roxy-command-center" / "last_exit.json"
            if not breadcrumb_path.exists():
                print("[App] No previous exit breadcrumb (first run or unexpected death)")
                return
            
            with open(breadcrumb_path) as f:
                data = json.load(f)
            
            reason = data.get("reason", "unknown")
            ts = data.get("ts", "unknown")
            prev_pid = data.get("pid", "unknown")
            
            if reason.startswith("signal:") or reason == "user_close":
                print(f"[App] Previous exit was clean: {reason} at {ts} (PID {prev_pid})")
            else:
                print(f"[App] WARNING: Previous exit was unexpected: {reason} at {ts} (PID {prev_pid})")
        except Exception as e:
            print(f"[App] Warning: Could not read previous exit breadcrumb: {e}")
    
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
        print("[MainWindow] ========== INIT BEGIN ==========")
        super().__init__(application=app)
        self.app = app
        self.add_css_class("roxy-command-center")
        print("[MainWindow] Window class initialized")
        
        # Window properties
        self.set_title("Roxy Command Center - Phase 2C Review")
        self.set_default_size(1280, 800)
        self.set_size_request(800, 600)
        print("[MainWindow] Window properties set")
        
        # Data
        self._daemon_client = DaemonClient()
        self._current_data: dict = {}
        self._poll_source_id: Optional[int] = None
        print("[MainWindow] Data structures initialized")
        
        # Initialize alert manager with app
        print("[MainWindow] Initializing alert manager...")
        get_alert_manager(app)
        print("[MainWindow] Alert manager initialized")
        
        # Build UI
        print("[MainWindow] Building UI...")
        self._build_ui()
        print("[MainWindow] UI built successfully")
        
        # Initial manual snapshot only. This review build avoids background
        # polling so ROXY's low-idle state stays quiet.
        print("[MainWindow] Fetching initial manual snapshot...")
        self._fetch_data()
        print("[MainWindow] ========== INIT COMPLETE ==========")
    
    def _build_ui(self):
        """Build the main UI."""
        # Toast overlay (for notifications)
        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        # Main vertical box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._toast_overlay.set_child(main_box)
        
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
        
        # Navigate to HOME (the cockpit)
        self.navigation.navigate_to("home")
    
    def _setup_pages(self):
        """Set up navigation pages."""
        # Home Console - THE COCKPIT (default landing)
        self.home_page = HomeConsolePage(
            on_navigate=self._on_navigate
        )
        self.navigation.add_page("home", "Home", self.home_page, "go-home-symbolic")
        
        # Overview page (telemetry dashboard)
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

        # Roxy Status page - Phase 2C read-only recovery/control-plane view
        self.roxy_status_page = RoxyStatusPage()
        self.navigation.add_page("roxy_status", "Roxy Status", self.roxy_status_page, "emblem-ok-symbolic")

        # MOS Cockpit - closed-loop UI over existing MOS ingress/authority spine
        self.mos_cockpit_page = MOSCockpitPage()
        self.navigation.add_page("mos_cockpit", "MOS Cockpit", self.mos_cockpit_page, "network-workgroup-symbolic")
        
        # Ollama page
        self.ollama_page = OllamaPanel(
            on_model_unload=self._on_ollama_unload,
            on_refresh=self._fetch_data
        )
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

    def _on_ollama_unload(self, pool: str, model: str):
        """Model mutation is disabled in the review build."""
        print(f"[MainWindow] Read-only review build: unload disabled for {model} from {pool}")
        self._show_toast("Read-only review build: model unload is disabled", timeout=4)

    def _show_toast(self, message: str, timeout: int = 3):
        """Show a toast notification."""
        toast = Adw.Toast(title=message)
        toast.set_timeout(timeout)
        # Find toast overlay in the window
        # The MainWindow uses AdwApplicationWindow which has a built-in toast overlay
        # We need to add one if not present
        if hasattr(self, '_toast_overlay'):
            self._toast_overlay.add_toast(toast)
        else:
            print(f"[MainWindow] Toast: {message}")
    
    def _start_polling(self, interval_ms: int = 5000):
        """Take a one-time snapshot; periodic polling is disabled."""
        self._stop_polling()
        self._fetch_data()
        print("[MainWindow] Manual snapshot complete; background polling disabled")
    
    def _stop_polling(self):
        """Stop daemon polling."""
        if self._poll_source_id:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None
    
    def _restart_polling(self, interval_ms: int = None):
        """Refresh one manual snapshot."""
        self._start_polling(interval_ms or 0)
    
    def _on_poll_timer(self) -> bool:
        """Periodic poll callback."""
        self._fetch_data()
        return True  # Continue
    
    def _fetch_data(self):
        """Fetch data from daemon."""
        def on_data(response):
            # Handle DaemonResponse object
            if hasattr(response, 'data'):
                raw_data = response.data if response.data else {}
                if response.error:
                    raw_data['error'] = response.error
            else:
                raw_data = response if isinstance(response, dict) else {}
            
            if raw_data:
                # Normalize to canonical schema
                data = normalize_status(raw_data)
                self._current_data = data
                
                self._update_ui(data)
                
                # Update header mode
                mode = data.get("mode", "local")
                host = raw_data.get("remote_host", "")
                self.header.set_mode(mode, host)
                
                # Update header debug strip
                cpu_pct = data.get("cpu", {}).get("cpu_pct", 0)
                gpu_count = len(data.get("gpus", []))
                self.header.set_debug_info(cpu_pct, gpu_count)
                
                # Process alerts
                alert_manager = get_alert_manager()
                alert_manager.process_daemon_data(raw_data)
                
                # Update alert badge in navigation
                alert_count = alert_manager.get_alert_count()
                self.navigation.set_badge("alerts", alert_count)
        
        self._daemon_client.fetch_async(on_data)
    
    def _update_ui(self, data: dict):
        """Update all UI components with new data."""
        # Home Console
        self.home_page.update(data)
        
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
