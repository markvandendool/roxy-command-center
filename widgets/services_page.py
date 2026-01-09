#!/usr/bin/env python3
"""
Services page showing all monitored services.
ROXY-CMD-STORY-002: Service cards page.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Dict, Optional

from widgets.service_card import ServiceCard


class ServicesPage(Gtk.ScrolledWindow):
    """
    Page showing all monitored services.
    
    Features:
    - Service cards with status
    - Start/stop/restart controls
    - Health indicators
    - Filtering
    """
    
    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self._service_cards: Dict[str, ServiceCard] = {}
        self._build_ui()
    
    def _build_ui(self):
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        self.set_child(main_box)
        
        # Header with filter
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_box.append(header)
        
        title = Gtk.Label(label="Services")
        title.add_css_class("title-2")
        title.set_xalign(0)
        title.set_hexpand(True)
        header.append(title)
        
        # Filter dropdown
        filter_btn = Gtk.DropDown()
        filter_model = Gtk.StringList()
        for label in ["All", "Running", "Stopped", "Unhealthy"]:
            filter_model.append(label)
        filter_btn.set_model(filter_model)
        filter_btn.connect("notify::selected", self._on_filter_changed)
        header.append(filter_btn)
        
        # Refresh button
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh")
        refresh_btn.connect("clicked", self._on_refresh_clicked)
        header.append(refresh_btn)
        
        # Service cards container
        self.cards_box = Gtk.FlowBox()
        self.cards_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.cards_box.set_homogeneous(True)
        self.cards_box.set_min_children_per_line(1)
        self.cards_box.set_max_children_per_line(3)
        self.cards_box.set_column_spacing(16)
        self.cards_box.set_row_spacing(16)
        main_box.append(self.cards_box)
        
        # Empty state (initially hidden)
        self.empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.empty_box.set_valign(Gtk.Align.CENTER)
        self.empty_box.set_margin_top(48)
        self.empty_box.set_visible(False)
        main_box.append(self.empty_box)
        
        empty_icon = Gtk.Image.new_from_icon_name("system-run-symbolic")
        empty_icon.set_pixel_size(64)
        empty_icon.add_css_class("dim-label")
        self.empty_box.append(empty_icon)
        
        empty_title = Gtk.Label(label="No Services")
        empty_title.add_css_class("title-2")
        self.empty_box.append(empty_title)
        
        empty_desc = Gtk.Label(label="No services configured or daemon not responding")
        empty_desc.add_css_class("dim-label")
        self.empty_box.append(empty_desc)
        
        self._current_filter = "all"
    
    def _on_filter_changed(self, dropdown, pspec):
        """Handle filter change."""
        filters = ["all", "running", "stopped", "unhealthy"]
        self._current_filter = filters[dropdown.get_selected()]
        self._apply_filter()
    
    def _apply_filter(self):
        """Apply current filter to cards."""
        for card in self._service_cards.values():
            visible = True
            
            if self._current_filter == "running":
                visible = card.get_status() == "running"
            elif self._current_filter == "stopped":
                visible = card.get_status() in ("stopped", "inactive")
            elif self._current_filter == "unhealthy":
                visible = card.get_health() not in ("ok", "healthy")
            
            card.get_parent().set_visible(visible)
    
    def _on_refresh_clicked(self, button):
        """Request refresh."""
        # Get parent window and call refresh
        window = self.get_root()
        if window and hasattr(window, 'refresh'):
            window.refresh()
    
    def update(self, data: dict):
        """Update services from daemon data."""
        services = data.get("services", {})
        
        # Add/update cards
        for name, service_data in services.items():
            if name not in self._service_cards:
                # Create new card
                card = ServiceCard(
                    service_name=name,
                    display_name=service_data.get("display_name", name),
                    port=service_data.get("port")
                )
                self._service_cards[name] = card
                self.cards_box.append(card)
            
            # Update card
            card = self._service_cards[name]
            card.update(service_data)
        
        # Remove cards for services no longer present
        for name in list(self._service_cards.keys()):
            if name not in services:
                card = self._service_cards.pop(name)
                parent = card.get_parent()
                if parent:
                    self.cards_box.remove(parent)
        
        # Show/hide empty state
        self.empty_box.set_visible(len(self._service_cards) == 0)
        
        # Apply filter
        self._apply_filter()
    
    def get_service_names(self) -> list:
        """Get list of service names."""
        return list(self._service_cards.keys())
