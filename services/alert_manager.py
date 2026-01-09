#!/usr/bin/env python3
"""
Alert manager with threshold monitoring.
ROXY-CMD-STORY-019: Threshold monitoring, hysteresis, rate limiting.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gio
import time
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List, Any
from enum import Enum
from collections import deque

ALERT_LOG_PATH = Path.home() / ".local/share/roxy-command-center/alerts.jsonl"
CONFIG_PATH = Path.home() / ".config/roxy-command-center/alert_config.json"

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class AlertType(Enum):
    GPU_TEMP = "gpu_temp"
    GPU_VRAM = "gpu_vram"
    SERVICE_DOWN = "service_down"
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    REMOTE_ERROR = "remote_error"

@dataclass
class Alert:
    """An active or historical alert."""
    id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    timestamp: float
    source: str = ""
    acknowledged: bool = False
    cleared: bool = False
    clear_timestamp: Optional[float] = None

@dataclass
class ThresholdConfig:
    """Configuration for a threshold-based alert."""
    alert_type: AlertType
    warning_threshold: float
    critical_threshold: float
    hysteresis: float = 2.0  # Must drop this much below threshold to clear
    rate_limit_seconds: float = 60.0  # Minimum time between alerts of same type

class AlertManager:
    """
    Alert manager with threshold monitoring and notifications.
    
    Features:
    - Threshold monitoring with hysteresis (ORACLE-07 mitigation)
    - Rate limiting to prevent notification spam
    - Desktop notifications via Gio.Notification
    - Alert history persistence
    """
    
    DEFAULT_THRESHOLDS = {
        AlertType.GPU_TEMP: ThresholdConfig(
            alert_type=AlertType.GPU_TEMP,
            warning_threshold=70.0,
            critical_threshold=80.0,
            hysteresis=2.0
        ),
        AlertType.GPU_VRAM: ThresholdConfig(
            alert_type=AlertType.GPU_VRAM,
            warning_threshold=80.0,
            critical_threshold=95.0,
            hysteresis=5.0
        ),
        AlertType.HIGH_CPU: ThresholdConfig(
            alert_type=AlertType.HIGH_CPU,
            warning_threshold=80.0,
            critical_threshold=95.0,
            hysteresis=5.0
        ),
        AlertType.HIGH_MEMORY: ThresholdConfig(
            alert_type=AlertType.HIGH_MEMORY,
            warning_threshold=80.0,
            critical_threshold=95.0,
            hysteresis=5.0
        ),
    }
    
    def __init__(self, app: Optional[Gio.Application] = None):
        self.app = app
        self.thresholds = dict(self.DEFAULT_THRESHOLDS)
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=100)  # Last 100 alerts
        self._last_alert_time: Dict[str, float] = {}  # Rate limiting
        self._current_values: Dict[str, float] = {}  # Track current values for hysteresis
        self._callbacks: List[Callable[[Alert], None]] = []
        self.notifications_enabled = True
        
        # Load saved config
        self._load_config()
        
        # Ensure log directory exists
        ALERT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self):
        """Load alert configuration."""
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH) as f:
                    config = json.load(f)
                    self.notifications_enabled = config.get("notifications_enabled", True)
                    
                    # Load custom thresholds
                    for type_str, thresh_data in config.get("thresholds", {}).items():
                        try:
                            alert_type = AlertType(type_str)
                            if alert_type in self.thresholds:
                                self.thresholds[alert_type].warning_threshold = thresh_data.get("warning", self.thresholds[alert_type].warning_threshold)
                                self.thresholds[alert_type].critical_threshold = thresh_data.get("critical", self.thresholds[alert_type].critical_threshold)
                        except ValueError:
                            pass
        except Exception as e:
            print(f"[AlertManager] Config load error: {e}")
    
    def save_config(self):
        """Save alert configuration."""
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            config = {
                "notifications_enabled": self.notifications_enabled,
                "thresholds": {
                    t.alert_type.value: {
                        "warning": t.warning_threshold,
                        "critical": t.critical_threshold
                    }
                    for t in self.thresholds.values()
                }
            }
            tmp_path = CONFIG_PATH.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(config, f, indent=2)
            tmp_path.rename(CONFIG_PATH)
        except Exception as e:
            print(f"[AlertManager] Config save error: {e}")
    
    def add_callback(self, callback: Callable[[Alert], None]):
        """Add callback for new alerts."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[Alert], None]):
        """Remove callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def check_value(self, alert_type: AlertType, value: float, source: str = ""):
        """
        Check a value against thresholds.
        Handles hysteresis and rate limiting.
        """
        if alert_type not in self.thresholds:
            return
        
        config = self.thresholds[alert_type]
        alert_key = f"{alert_type.value}:{source}"
        prev_value = self._current_values.get(alert_key, 0)
        self._current_values[alert_key] = value
        
        # Check if we have an active alert for this
        active = self.active_alerts.get(alert_key)
        
        if active:
            # Check for clear condition (with hysteresis)
            if active.severity == AlertSeverity.CRITICAL:
                clear_threshold = config.critical_threshold - config.hysteresis
            else:
                clear_threshold = config.warning_threshold - config.hysteresis
            
            if value < clear_threshold:
                self._clear_alert(alert_key)
        else:
            # Check for new alert condition
            severity = None
            if value >= config.critical_threshold:
                severity = AlertSeverity.CRITICAL
            elif value >= config.warning_threshold:
                severity = AlertSeverity.WARNING
            
            if severity:
                self._create_alert(alert_type, severity, value, source, alert_key)
    
    def check_service(self, service_name: str, is_healthy: bool):
        """Check service health and create/clear alerts."""
        alert_key = f"service:{service_name}"
        
        if not is_healthy:
            if alert_key not in self.active_alerts:
                self._create_alert(
                    AlertType.SERVICE_DOWN,
                    AlertSeverity.CRITICAL,
                    0,
                    service_name,
                    alert_key
                )
        else:
            if alert_key in self.active_alerts:
                self._clear_alert(alert_key)
    
    def _create_alert(self, alert_type: AlertType, severity: AlertSeverity,
                      value: float, source: str, alert_key: str):
        """Create a new alert if rate limit allows."""
        now = time.time()
        
        # Check rate limit
        last_time = self._last_alert_time.get(alert_key, 0)
        config = self.thresholds.get(alert_type)
        rate_limit = config.rate_limit_seconds if config else 60.0
        
        if now - last_time < rate_limit:
            return  # Rate limited
        
        self._last_alert_time[alert_key] = now
        
        # Create alert
        alert_id = f"{alert_key}:{int(now)}"
        
        # Generate title and message
        if alert_type == AlertType.GPU_TEMP:
            title = f"GPU Temperature {severity.value.upper()}"
            message = f"{source}: {value:.0f}°C"
        elif alert_type == AlertType.GPU_VRAM:
            title = f"GPU VRAM {severity.value.upper()}"
            message = f"{source}: {value:.0f}% used"
        elif alert_type == AlertType.SERVICE_DOWN:
            title = "Service Down"
            message = f"{source} is not responding"
        elif alert_type == AlertType.HIGH_CPU:
            title = f"CPU Usage {severity.value.upper()}"
            message = f"{value:.0f}% CPU usage"
        elif alert_type == AlertType.HIGH_MEMORY:
            title = f"Memory Usage {severity.value.upper()}"
            message = f"{value:.0f}% memory used"
        else:
            title = f"Alert: {alert_type.value}"
            message = f"{source}: {value}"
        
        alert = Alert(
            id=alert_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            timestamp=now,
            source=source
        )
        
        self.active_alerts[alert_key] = alert
        self.alert_history.append(alert)
        self._log_alert(alert)
        
        # Send notification
        if self.notifications_enabled:
            self._send_notification(alert)
        
        # Notify callbacks
        for cb in self._callbacks:
            try:
                cb(alert)
            except Exception as e:
                print(f"[AlertManager] Callback error: {e}")
    
    def _clear_alert(self, alert_key: str):
        """Clear an active alert."""
        if alert_key not in self.active_alerts:
            return
        
        alert = self.active_alerts.pop(alert_key)
        alert.cleared = True
        alert.clear_timestamp = time.time()
        
        self._log_alert(alert, cleared=True)
    
    def _send_notification(self, alert: Alert):
        """Send desktop notification."""
        if not self.app:
            return
        
        try:
            notification = Gio.Notification.new(alert.title)
            notification.set_body(alert.message)
            
            if alert.severity == AlertSeverity.CRITICAL:
                notification.set_priority(Gio.NotificationPriority.URGENT)
            elif alert.severity == AlertSeverity.WARNING:
                notification.set_priority(Gio.NotificationPriority.HIGH)
            else:
                notification.set_priority(Gio.NotificationPriority.NORMAL)
            
            self.app.send_notification(alert.id, notification)
        except Exception as e:
            print(f"[AlertManager] Notification error: {e}")
    
    def _log_alert(self, alert: Alert, cleared: bool = False):
        """Append alert to log file."""
        try:
            entry = {
                "id": alert.id,
                "type": alert.alert_type.value,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "source": alert.source,
                "timestamp": alert.timestamp,
                "cleared": cleared,
                "clear_timestamp": alert.clear_timestamp
            }
            with open(ALERT_LOG_PATH, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[AlertManager] Log error: {e}")
    
    def acknowledge_alert(self, alert_key: str):
        """Acknowledge an alert (stops repeat notifications)."""
        if alert_key in self.active_alerts:
            self.active_alerts[alert_key].acknowledged = True
    
    def dismiss_alert(self, alert_key: str):
        """Dismiss (clear) an alert."""
        self._clear_alert(alert_key)
    
    def get_active_alerts(self) -> List[Alert]:
        """Get list of active alerts."""
        return list(self.active_alerts.values())
    
    def get_alert_count(self, severity: Optional[AlertSeverity] = None) -> int:
        """Get count of active alerts, optionally filtered by severity."""
        if severity:
            return sum(1 for a in self.active_alerts.values() if a.severity == severity)
        return len(self.active_alerts)
    
    def get_unacknowledged_count(self) -> int:
        """Get count of unacknowledged alerts."""
        return sum(1 for a in self.active_alerts.values() if not a.acknowledged)
    
    def process_daemon_data(self, data: dict):
        """Process daemon data and check all thresholds."""
        # GPU checks
        gpus = data.get("gpus", [])
        for i, gpu in enumerate(gpus):
            source = gpu.get("name", f"GPU{i}")
            
            # Temperature
            temp = gpu.get("temp", 0)
            if temp > 0:
                self.check_value(AlertType.GPU_TEMP, temp, source)
            
            # VRAM
            vram_used = gpu.get("vram_used_gb", 0)
            vram_total = gpu.get("vram_total_gb", 1)
            vram_percent = (vram_used / vram_total * 100) if vram_total > 0 else 0
            if vram_percent > 0:
                self.check_value(AlertType.GPU_VRAM, vram_percent, source)
        
        # CPU check
        system = data.get("system", {})
        cpu_percent = system.get("cpu_percent", 0)
        if cpu_percent > 0:
            self.check_value(AlertType.HIGH_CPU, cpu_percent, "CPU")
        
        # Memory check
        mem_used = system.get("mem_used_gb", 0)
        mem_total = system.get("mem_total_gb", 1)
        mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0
        if mem_percent > 0:
            self.check_value(AlertType.HIGH_MEMORY, mem_percent, "Memory")
        
        # Service checks
        services = data.get("services", {})
        for name, service in services.items():
            health = service.get("health", "unknown")
            is_healthy = health in ("ok", "healthy")
            self.check_service(name, is_healthy)


# Global instance
_alert_manager: Optional[AlertManager] = None

def get_alert_manager(app: Optional[Gio.Application] = None) -> AlertManager:
    """Get or create global alert manager."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager(app)
    elif app and not _alert_manager.app:
        _alert_manager.app = app
    return _alert_manager
