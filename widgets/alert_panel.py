#!/usr/bin/env python3
"""
Alert panel widget for displaying active alerts.
ROXY-CMD-STORY-020: Alert panel with badge, list, and actions.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango
import time
from typing import Optional

from services.alert_manager import (
    get_alert_manager, Alert, AlertSeverity, AlertManager
)


class AlertRow(Gtk.ListBoxRow):
    """A single alert row with actions."""
    
    def __init__(self, alert: Alert, on_dismiss: callable):
        super().__init__()
        self.alert = alert
        self.on_dismiss = on_dismiss
        self.add_css_class("alert-row")
        
        # Add severity class
        self.add_css_class(f"alert-{alert.severity.value}")
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        self.set_child(box)
        
        # Severity icon
        icon_name = self._get_severity_icon()
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(24)
        icon.add_css_class(f"alert-icon-{alert.severity.value}")
        box.append(icon)
        
        # Content box
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content.set_hexpand(True)
        box.append(content)
        
        # Title
        title_label = Gtk.Label(label=alert.title)
        title_label.set_xalign(0)
        title_label.add_css_class("alert-title")
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        content.append(title_label)
        
        # Message + time
        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.append(meta_box)
        
        msg_label = Gtk.Label(label=alert.message)
        msg_label.set_xalign(0)
        msg_label.add_css_class("alert-message")
        msg_label.add_css_class("dim-label")
        msg_label.set_ellipsize(Pango.EllipsizeMode.END)
        msg_label.set_hexpand(True)
        meta_box.append(msg_label)
        
        # Time ago
        time_str = self._format_time_ago(alert.timestamp)
        time_label = Gtk.Label(label=time_str)
        time_label.add_css_class("alert-time")
        time_label.add_css_class("dim-label")
        meta_box.append(time_label)
        
        # Dismiss button
        dismiss_btn = Gtk.Button.new_from_icon_name("window-close-symbolic")
        dismiss_btn.set_valign(Gtk.Align.CENTER)
        dismiss_btn.add_css_class("flat")
        dismiss_btn.add_css_class("circular")
        dismiss_btn.set_tooltip_text("Dismiss alert")
        dismiss_btn.connect("clicked", self._on_dismiss)
        box.append(dismiss_btn)
    
    def _get_severity_icon(self) -> str:
        icons = {
            AlertSeverity.CRITICAL: "dialog-error-symbolic",
            AlertSeverity.WARNING: "dialog-warning-symbolic",
            AlertSeverity.INFO: "dialog-information-symbolic",
        }
        return icons.get(self.alert.severity, "dialog-information-symbolic")
    
    def _format_time_ago(self, timestamp: float) -> str:
        diff = time.time() - timestamp
        if diff < 60:
            return "just now"
        elif diff < 3600:
            mins = int(diff / 60)
            return f"{mins}m ago"
        elif diff < 86400:
            hours = int(diff / 3600)
            return f"{hours}h ago"
        else:
            days = int(diff / 86400)
            return f"{days}d ago"
    
    def _on_dismiss(self, button):
        if self.on_dismiss:
            self.on_dismiss(self.alert)


class AlertPanel(Gtk.Box):
    """
    Alert panel showing active alerts.
    
    Features:
    - Alert list with severity icons
    - Dismiss and acknowledge actions
    - Real-time updates
    - Empty state
    """
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("alert-panel")
        
        self.alert_manager = get_alert_manager()
        self.alert_manager.add_callback(self._on_new_alert)
        
        self._build_ui()
        self._refresh_alerts()
    
    def _build_ui(self):
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(12)
        header.set_margin_bottom(12)
        header.set_margin_start(12)
        header.set_margin_end(12)
        self.append(header)
        
        # Title with badge
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box.set_hexpand(True)
        header.append(title_box)
        
        title = Gtk.Label(label="Active Alerts")
        title.add_css_class("title-4")
        title_box.append(title)
        
        # Count badge
        self.count_badge = Gtk.Label(label="0")
        self.count_badge.add_css_class("alert-badge")
        self.count_badge.add_css_class("numeric")
        self.count_badge.set_visible(False)
        title_box.append(self.count_badge)
        
        # Clear all button
        self.clear_all_btn = Gtk.Button(label="Clear All")
        self.clear_all_btn.add_css_class("flat")
        self.clear_all_btn.connect("clicked", self._on_clear_all)
        self.clear_all_btn.set_sensitive(False)
        header.append(self.clear_all_btn)
        
        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)
        
        # Scrolled window for alerts
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scrolled)
        
        # Stack for list/empty state
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        scrolled.set_child(self.stack)
        
        # Alert list
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        self.stack.add_named(self.list_box, "list")
        
        # Empty state
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_margin_top(48)
        empty_box.set_margin_bottom(48)
        self.stack.add_named(empty_box, "empty")
        
        empty_icon = Gtk.Image.new_from_icon_name("weather-clear-symbolic")
        empty_icon.set_pixel_size(64)
        empty_icon.add_css_class("dim-label")
        empty_box.append(empty_icon)
        
        empty_title = Gtk.Label(label="All Clear")
        empty_title.add_css_class("title-2")
        empty_box.append(empty_title)
        
        empty_desc = Gtk.Label(label="No active alerts")
        empty_desc.add_css_class("dim-label")
        empty_box.append(empty_desc)
        
        # Start refresh timer
        GLib.timeout_add_seconds(5, self._on_refresh_timer)
    
    def _refresh_alerts(self):
        """Refresh the alert list."""
        alerts = self.alert_manager.get_active_alerts()
        
        # Clear existing
        while True:
            row = self.list_box.get_row_at_index(0)
            if row:
                self.list_box.remove(row)
            else:
                break
        
        # Sort by severity, then timestamp
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.WARNING: 1,
            AlertSeverity.INFO: 2
        }
        alerts.sort(key=lambda a: (severity_order.get(a.severity, 3), -a.timestamp))
        
        # Add rows
        for alert in alerts:
            row = AlertRow(alert, self._on_dismiss_alert)
            self.list_box.append(row)
        
        # Update badge
        count = len(alerts)
        self.count_badge.set_label(str(count))
        self.count_badge.set_visible(count > 0)
        self.clear_all_btn.set_sensitive(count > 0)
        
        # Update badge severity
        self.count_badge.remove_css_class("alert-badge-critical")
        self.count_badge.remove_css_class("alert-badge-warning")
        
        critical_count = self.alert_manager.get_alert_count(AlertSeverity.CRITICAL)
        if critical_count > 0:
            self.count_badge.add_css_class("alert-badge-critical")
        elif count > 0:
            self.count_badge.add_css_class("alert-badge-warning")
        
        # Show list or empty state
        self.stack.set_visible_child_name("list" if count > 0 else "empty")
    
    def _on_new_alert(self, alert: Alert):
        """Callback when new alert is created."""
        GLib.idle_add(self._refresh_alerts)
    
    def _on_dismiss_alert(self, alert: Alert):
        """Dismiss a single alert."""
        alert_key = f"{alert.alert_type.value}:{alert.source}"
        self.alert_manager.dismiss_alert(alert_key)
        self._refresh_alerts()
    
    def _on_clear_all(self, button):
        """Clear all active alerts."""
        alerts = list(self.alert_manager.active_alerts.keys())
        for key in alerts:
            self.alert_manager.dismiss_alert(key)
        self._refresh_alerts()
    
    def _on_refresh_timer(self) -> bool:
        """Periodic refresh for time display."""
        self._refresh_alerts()
        return True  # Continue timer
    
    def get_badge_widget(self) -> Gtk.Widget:
        """Get a badge widget for use in navigation."""
        badge = AlertBadge(self.alert_manager)
        return badge


class AlertBadge(Gtk.Label):
    """
    Compact badge showing alert count.
    For use in navigation tabs or header.
    """
    
    def __init__(self, alert_manager: Optional[AlertManager] = None):
        super().__init__()
        self.alert_manager = alert_manager or get_alert_manager()
        self.alert_manager.add_callback(self._on_alert_change)
        
        self.add_css_class("alert-badge")
        self.add_css_class("numeric")
        self.set_visible(False)
        
        self._update()
        GLib.timeout_add_seconds(5, self._on_timer)
    
    def _update(self):
        count = self.alert_manager.get_alert_count()
        critical = self.alert_manager.get_alert_count(AlertSeverity.CRITICAL)
        
        self.set_label(str(count))
        self.set_visible(count > 0)
        
        self.remove_css_class("alert-badge-critical")
        self.remove_css_class("alert-badge-warning")
        
        if critical > 0:
            self.add_css_class("alert-badge-critical")
        elif count > 0:
            self.add_css_class("alert-badge-warning")
    
    def _on_alert_change(self, alert: Alert):
        GLib.idle_add(self._update)
    
    def _on_timer(self) -> bool:
        self._update()
        return True
