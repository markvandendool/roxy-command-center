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
from widgets.performance_page import PerformancePage
from widgets.apps_page import AppsPage
from widgets.agents_page import AgentsPage
from widgets.brain_page import BrainPage
from widgets.executive_page import ExecutivePage
from widgets.voice_actions_page import VoiceActionsPage
from widgets.content_business_page import ContentBusinessPage
from widgets.receipts_proof_page import ReceiptsProofPage
from widgets.storage_hygiene_page import StorageHygienePage
from services.alert_manager import get_alert_manager
from services.ollama_control import get_ollama_control, OllamaAction, ActionResult
from services.telemetry_collector import get_collector

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
        self.set_title("Roxy Command Center")
        self.set_default_size(1280, 800)
        self.set_size_request(800, 600)
        print("[MainWindow] Window properties set")
        
        # Detect small-screen monitor (e.g. GWD 15" 1920×1080) and apply compact mode
        self._compact_mode = os.getenv("ROXY_CC_COMPACT", "0") == "1"
        self._target_monitor = None
        self.connect("realize", self._on_window_realize)
        if self._compact_mode:
            self.add_css_class("compact-mode")
            print("[MainWindow] Compact mode enabled (GWD/small screen)")
        
        # Data
        self._daemon_client = DaemonClient()
        self._current_data: dict = {}
        self._poll_source_id: Optional[int] = None
        self._is_visible = True
        self._refresh_interval_ms = 5000
        print("[MainWindow] Data structures initialized")
        
        # Initialize alert manager with app
        print("[MainWindow] Initializing alert manager...")
        get_alert_manager(app)
        print("[MainWindow] Alert manager initialized")
        
        # Build UI
        print("[MainWindow] Building UI...")
        self._build_ui()
        print("[MainWindow] UI built successfully")
        
        # Visibility detection for adaptive refresh
        self.connect("notify::visible", self._on_visibility_changed)
        
        # Live polling for real-time telemetry and sparkline history.
        # Adaptive: 5s when visible, 30s when backgrounded.
        print("[MainWindow] Starting live polling...")
        self._start_polling(5000)
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
        self.navigation.stack.connect("notify::visible-child-name", self._on_visible_page_changed)
        
        # The hard-surface daily-driver opens on live LifePanel truth. The chat
        # console remains available as a lazy page so mock triage/run scaffolding
        # does not own the dedicated monitor at startup.
        start_page = os.getenv("ROXY_CC_START_PAGE", "overview")
        self.navigation.navigate_to(start_page)
    
    def _setup_pages(self):
        """Set up navigation pages — LifePanel layout."""
        # Home Console — lazy, because it owns chat connection setup and review
        # build triage placeholders.
        self.home_page = None
        self.navigation.add_lazy_page("home", "Home", self._build_home_page, "go-home-symbolic")
        
        # Overview — LifePanel home
        self.overview_page = OverviewPage(on_navigate=self._on_navigate)
        self.navigation.add_page("overview", "Overview", self.overview_page, "view-grid-symbolic")
        
        # Performance
        self.performance_page = PerformancePage()
        self.navigation.add_page("performance", "Performance", self.performance_page, "preferences-system-symbolic")
        
        # Apps
        self.apps_page = AppsPage()
        self.navigation.add_page("apps", "Apps", self.apps_page, "applications-utilities-symbolic")
        
        # Agents
        self.agents_page = AgentsPage()
        self.navigation.add_page("agents", "Agents", self.agents_page, "applications-games-symbolic")
        
        # Brain
        self.brain_page = BrainPage()
        self.navigation.add_page("brain", "Brain", self.brain_page, "preferences-system-symbolic")
        
        # Executive
        self.executive_page = ExecutivePage()
        self.navigation.add_page("executive", "Executive", self.executive_page, "emblem-ok-symbolic")
        
        # Voice / Actions
        self.voice_actions_page = VoiceActionsPage()
        self.navigation.add_page("voice_actions", "Voice / Actions", self.voice_actions_page, "audio-input-microphone-symbolic")
        
        # Content
        self.content_page = ContentBusinessPage()
        self.navigation.add_page("content", "Content", self.content_page, "folder-music-symbolic")
        
        # Receipts / Proof
        self.receipts_page = ReceiptsProofPage()
        self.navigation.add_page("receipts", "Receipts", self.receipts_page, "emblem-ok-symbolic")
        
        # Storage / Hygiene
        self.storage_page = StorageHygienePage()
        self.navigation.add_page("storage", "Storage", self.storage_page, "drive-harddisk-symbolic")
        
        # Services
        self.services_page = ServicesPage()
        self.navigation.add_page("services", "Services", self.services_page, "system-run-symbolic")
        
        # GPUs
        self.gpus_page = GpusPage()
        self.navigation.add_page("gpus", "GPUs", self.gpus_page, "video-display-symbolic")

        # Roxy Status
        self.roxy_status_page = RoxyStatusPage()
        self.navigation.add_page("roxy_status", "Roxy Status", self.roxy_status_page, "emblem-ok-symbolic")

        # MOS Cockpit
        self.mos_cockpit_page = MOSCockpitPage()
        self.navigation.add_page("mos_cockpit", "MOS Cockpit", self.mos_cockpit_page, "network-workgroup-symbolic")
        
        # Ollama
        self.ollama_page = OllamaPanel(
            on_model_unload=self._on_ollama_unload,
            on_refresh=self._fetch_data
        )
        self.navigation.add_page("ollama", "Ollama", self.ollama_page, "face-smile-big-symbolic")
        
        # Alerts
        self.alerts_page = AlertPanel()
        self.navigation.add_page("alerts", "Alerts", self.alerts_page, "dialog-warning-symbolic")
        
        # Terminal
        self.terminal_page = TerminalPage()
        self.navigation.add_page("terminal", "Terminal", self.terminal_page, "utilities-terminal-symbolic")
        
        # Settings
        self.settings_page = SettingsPage(on_setting_changed=self._on_setting_changed)
        self.navigation.add_page("settings", "Settings", self.settings_page, "emblem-system-symbolic")

    def _build_home_page(self):
        """Build the operator chat page on demand."""
        self.home_page = HomeConsolePage(on_navigate=self._on_navigate)
        return self.home_page
    
    def _on_navigate(self, page_id: str):
        """Handle navigation from overview cards or sidebar.
        
        Immediately hydrate the newly visible page with current data
        so it doesn't sit at zeros until the next timer tick.
        """
        self.navigation.navigate_to(page_id)
        
        if self._current_data:
            self._hydrate_current_page(self._current_data)

    def _on_visible_page_changed(self, stack, param):
        """Hydrate pages selected through the sidebar after the initial snapshot."""
        if self._current_data:
            self._hydrate_current_page(self._current_data)

    def _hydrate_current_page(self, data: dict):
        """Update the selected heavy page from the latest cached snapshot."""
        visible_name = self.navigation.get_current_page()
        page_map = {
            "performance": self.performance_page,
            "apps": self.apps_page,
            "agents": self.agents_page,
            "brain": self.brain_page,
            "executive": self.executive_page,
            "voice_actions": self.voice_actions_page,
            "content": self.content_page,
            "receipts": self.receipts_page,
            "storage": self.storage_page,
            "services": self.services_page,
            "gpus": self.gpus_page,
            "roxy_status": self.roxy_status_page,
            "mos_cockpit": self.mos_cockpit_page,
            "ollama": self.ollama_page,
            "alerts": self.alerts_page,
            "terminal": self.terminal_page,
        }
        if visible_name == "home" and self.home_page is not None:
            self.home_page.update(data)
        elif visible_name in page_map:
            page_map[visible_name].update(data)
    
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
        """Start adaptive polling: 5s visible, 30s background."""
        self._stop_polling()
        self._refresh_interval_ms = interval_ms if self._is_visible else 30000
        self._fetch_data()
        self._poll_source_id = GLib.timeout_add(self._refresh_interval_ms, self._on_poll_timer)
        print(f"[MainWindow] Polling: {self._refresh_interval_ms}ms (visible={self._is_visible})")
    
    def _stop_polling(self):
        """Stop daemon polling."""
        if self._poll_source_id:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None
    
    def _restart_polling(self, interval_ms: int = None):
        """Restart polling with adaptive interval."""
        self._start_polling(interval_ms or 5000)
    
    def _on_visibility_changed(self, widget, param):
        """Adapt refresh rate based on window visibility."""
        visible = self.get_visible()
        if visible != self._is_visible:
            self._is_visible = visible
            self._restart_polling()
    
    def _on_window_realize(self, widget):
        """After window is realized, detect monitor and apply compact mode if needed."""
        display = self.get_display()
        if not display:
            return
        
        surface = self.get_surface()
        if not surface:
            return
        
        # Check which monitor the window is on
        monitor = display.get_monitor_at_surface(surface)
        if monitor:
            geom = monitor.get_geometry()
            print(f"[MainWindow] On monitor: {geom.width}x{geom.height} at {geom.x},{geom.y}")
            
            # Auto-enable compact mode for small monitors (<= 1080 height)
            if geom.height <= 1080 and not self._compact_mode:
                self._compact_mode = True
                self.add_css_class("compact-mode")
                print(f"[MainWindow] Auto-compact: monitor height {geom.height}px")
            
            # If compact, still respect start page preference
            if self._compact_mode:
                start_page = os.getenv("ROXY_CC_START_PAGE", "overview")
                print(f"[MainWindow] Compact mode: navigating to {start_page}")
                GLib.idle_add(lambda: self.navigation.navigate_to(start_page) or False)
    
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
                
                # Accumulate telemetry history for sparklines
                get_collector().push(data)
                
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
        """Update only the visible page + overview badges. Off-screen pages stay frozen.
        
        GTK4 Stack shows one child at a time. Updating invisible pages wastes CPU
        on Cairo sparklines, table rebuilds, and label repaints.
        """
        # Overview always updates (it's the LifePanel summary dashboard)
        # It self-throttles sparkline redraws when not visible
        self.overview_page.update(data)
        
        # Home page is lazy. Only update it after the operator explicitly opens it.
        if self.home_page is not None:
            self.home_page.update(data)
        
        # Only the visible page gets heavy update (tables, graphs, process lists)
        self._hydrate_current_page(data)
        
        # Nav badges always update (lightweight — just label text)
        perf = data.get("performance", {})
        agents = perf.get("agents", {})
        abandoned = agents.get("abandoned", 0)
        if abandoned > 0:
            self.navigation.set_badge("agents", abandoned)
        else:
            self.navigation.set_badge("agents", 0)
        
        perf_status = perf.get("status", "")
        if perf_status in ("warn", "blocked"):
            self.navigation.set_badge("performance", 1)
        else:
            self.navigation.set_badge("performance", 0)
        
        # Brain badge if degraded
        brain = data.get("brainAuthority", {})
        if brain.get("status") != "healthy":
            self.navigation.set_badge("brain", 1)
        else:
            self.navigation.set_badge("brain", 0)
        
        # Storage badge if swap > 80%
        host_mem = data.get("hostMemory", {})
        swap = host_mem.get("swap", {})
        swap_total = swap.get("swapTotalGb", 0) or swap.get("totalGb", 1)
        swap_used = swap.get("swapUsedGb", 0) or swap.get("usedGb", 0)
        swap_pct = (swap_used / swap_total * 100) if swap_total > 0 else 0
        if swap_pct > 80:
            self.navigation.set_badge("storage", int(swap_pct))
        else:
            self.navigation.set_badge("storage", 0)
    
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
