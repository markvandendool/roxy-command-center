#!/usr/bin/env python3
"""
D-Bus systemd service control.
ROXY-CMD-STORY-003: pydbus integration for StartUnit/StopUnit/RestartUnit.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gio
from typing import Optional, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
import threading

class ServiceScope(Enum):
    """Systemd service scope."""
    USER = "user"
    SYSTEM = "system"
    UNKNOWN = "unknown"

class ActionResult(Enum):
    """Service action result."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ACCESS_DENIED = "access_denied"
    NOT_FOUND = "not_found"

@dataclass
class ServiceAction:
    """Result of a service action."""
    service: str
    action: str
    result: ActionResult
    message: str = ""
    new_state: str = ""

class SystemdControl:
    """
    D-Bus interface to systemd for service control.
    
    Features:
    - Detect user vs system services (ORACLE-02 mitigation)
    - Non-blocking actions via thread pool
    - Polkit-aware error handling
    - Action cooldown tracking
    """
    
    # Known Roxy services
    KNOWN_SERVICES = {
        "roxy-core": "roxy-core.service",
        "roxy_core": "roxy-core.service",
        "ollama-big": "ollama-big.service",
        "ollama_big": "ollama-big.service",
        "ollama-fast": "ollama-fast.service",
        "ollama_fast": "ollama-fast.service",
    }
    
    def __init__(self):
        self._user_bus: Optional[Gio.DBusConnection] = None
        self._system_bus: Optional[Gio.DBusConnection] = None
        self._cooldowns: dict = {}  # service -> timestamp
        self.cooldown_seconds = 5.0
    
    def _get_user_bus(self) -> Gio.DBusConnection:
        """Get user session D-Bus connection."""
        if self._user_bus is None:
            self._user_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return self._user_bus
    
    def _get_system_bus(self) -> Gio.DBusConnection:
        """Get system D-Bus connection."""
        if self._system_bus is None:
            self._system_bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        return self._system_bus
    
    def normalize_service_name(self, service: str) -> str:
        """Convert display name to systemd unit name."""
        if service in self.KNOWN_SERVICES:
            return self.KNOWN_SERVICES[service]
        if not service.endswith(".service"):
            return f"{service}.service"
        return service
    
    def detect_scope(self, service: str) -> ServiceScope:
        """
        Detect if service is user-level or system-level.
        Tries user bus first, falls back to system.
        """
        unit_name = self.normalize_service_name(service)
        
        # Try user scope first
        try:
            bus = self._get_user_bus()
            result = bus.call_sync(
                "org.freedesktop.systemd1",
                "/org/freedesktop/systemd1",
                "org.freedesktop.systemd1.Manager",
                "GetUnit",
                GLib.Variant("(s)", (unit_name,)),
                GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE,
                1000,  # 1s timeout
                None
            )
            if result:
                return ServiceScope.USER
        except GLib.Error:
            pass
        
        # Try system scope
        try:
            bus = self._get_system_bus()
            result = bus.call_sync(
                "org.freedesktop.systemd1",
                "/org/freedesktop/systemd1",
                "org.freedesktop.systemd1.Manager",
                "GetUnit",
                GLib.Variant("(s)", (unit_name,)),
                GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE,
                1000,
                None
            )
            if result:
                return ServiceScope.SYSTEM
        except GLib.Error:
            pass
        
        return ServiceScope.UNKNOWN
    
    def get_service_state(self, service: str) -> Tuple[str, str]:
        """
        Get service active state and sub-state.
        Returns (active_state, sub_state) e.g. ("active", "running")
        """
        unit_name = self.normalize_service_name(service)
        scope = self.detect_scope(service)
        
        if scope == ServiceScope.UNKNOWN:
            return ("unknown", "not-found")
        
        bus = self._get_user_bus() if scope == ServiceScope.USER else self._get_system_bus()
        
        try:
            # Get unit path
            result = bus.call_sync(
                "org.freedesktop.systemd1",
                "/org/freedesktop/systemd1",
                "org.freedesktop.systemd1.Manager",
                "GetUnit",
                GLib.Variant("(s)", (unit_name,)),
                GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE,
                2000,
                None
            )
            unit_path = result.get_child_value(0).get_string()
            
            # Get ActiveState property
            active_result = bus.call_sync(
                "org.freedesktop.systemd1",
                unit_path,
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", ("org.freedesktop.systemd1.Unit", "ActiveState")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE,
                2000,
                None
            )
            active_state = active_result.get_child_value(0).get_variant().get_string()
            
            # Get SubState property
            sub_result = bus.call_sync(
                "org.freedesktop.systemd1",
                unit_path,
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", ("org.freedesktop.systemd1.Unit", "SubState")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE,
                2000,
                None
            )
            sub_state = sub_result.get_child_value(0).get_variant().get_string()
            
            return (active_state, sub_state)
            
        except GLib.Error as e:
            return ("error", str(e))
    
    def is_on_cooldown(self, service: str) -> bool:
        """Check if service action is on cooldown."""
        import time
        unit_name = self.normalize_service_name(service)
        if unit_name not in self._cooldowns:
            return False
        elapsed = time.time() - self._cooldowns[unit_name]
        return elapsed < self.cooldown_seconds
    
    def get_cooldown_remaining(self, service: str) -> float:
        """Get remaining cooldown seconds."""
        import time
        unit_name = self.normalize_service_name(service)
        if unit_name not in self._cooldowns:
            return 0.0
        elapsed = time.time() - self._cooldowns[unit_name]
        remaining = self.cooldown_seconds - elapsed
        return max(0.0, remaining)
    
    def _set_cooldown(self, service: str):
        """Set cooldown for service."""
        import time
        unit_name = self.normalize_service_name(service)
        self._cooldowns[unit_name] = time.time()
    
    def start_service(self, service: str, callback: Optional[Callable[[ServiceAction], None]] = None):
        """Start a service asynchronously."""
        self._do_action(service, "StartUnit", "start", callback)
    
    def stop_service(self, service: str, callback: Optional[Callable[[ServiceAction], None]] = None):
        """Stop a service asynchronously."""
        self._do_action(service, "StopUnit", "stop", callback)
    
    def restart_service(self, service: str, callback: Optional[Callable[[ServiceAction], None]] = None):
        """Restart a service asynchronously."""
        self._do_action(service, "RestartUnit", "restart", callback)
    
    def _do_action(self, service: str, method: str, action_name: str, 
                   callback: Optional[Callable[[ServiceAction], None]] = None):
        """Execute service action in background thread."""
        if self.is_on_cooldown(service):
            if callback:
                result = ServiceAction(
                    service=service,
                    action=action_name,
                    result=ActionResult.FAILED,
                    message=f"On cooldown ({self.get_cooldown_remaining(service):.1f}s remaining)"
                )
                GLib.idle_add(lambda: callback(result))
            return
        
        def worker():
            result = self._do_action_sync(service, method, action_name)
            if result.result == ActionResult.SUCCESS:
                self._set_cooldown(service)
            if callback:
                GLib.idle_add(lambda: callback(result))
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
    
    def _do_action_sync(self, service: str, method: str, action_name: str) -> ServiceAction:
        """Synchronous service action (runs in worker thread)."""
        unit_name = self.normalize_service_name(service)
        scope = self.detect_scope(service)
        
        if scope == ServiceScope.UNKNOWN:
            return ServiceAction(
                service=service,
                action=action_name,
                result=ActionResult.NOT_FOUND,
                message=f"Service {unit_name} not found in user or system scope"
            )
        
        bus = self._get_user_bus() if scope == ServiceScope.USER else self._get_system_bus()
        
        try:
            result = bus.call_sync(
                "org.freedesktop.systemd1",
                "/org/freedesktop/systemd1",
                "org.freedesktop.systemd1.Manager",
                method,
                GLib.Variant("(ss)", (unit_name, "replace")),
                GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE,
                30000,  # 30s timeout for slow services
                None
            )
            
            # Get new state
            import time
            time.sleep(0.5)  # Brief pause for state to settle
            new_state, sub_state = self.get_service_state(service)
            
            return ServiceAction(
                service=service,
                action=action_name,
                result=ActionResult.SUCCESS,
                message=f"Service {action_name} completed",
                new_state=f"{new_state} ({sub_state})"
            )
            
        except GLib.Error as e:
            error_msg = str(e)
            
            if "AccessDenied" in error_msg or "not authorized" in error_msg.lower():
                return ServiceAction(
                    service=service,
                    action=action_name,
                    result=ActionResult.ACCESS_DENIED,
                    message="Permission denied. System service requires elevated privileges."
                )
            
            return ServiceAction(
                service=service,
                action=action_name,
                result=ActionResult.FAILED,
                message=error_msg
            )


# Global instance
_systemd: Optional[SystemdControl] = None

def get_systemd() -> SystemdControl:
    """Get or create global systemd control instance."""
    global _systemd
    if _systemd is None:
        _systemd = SystemdControl()
    return _systemd
