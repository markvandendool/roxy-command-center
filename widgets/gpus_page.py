#!/usr/bin/env python3
"""
GPUs page showing all GPU cards.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Dict

from widgets.gpu_card import GPUCard as GpuCard


class GpusPage(Gtk.ScrolledWindow):
    """
    Page showing all GPUs.
    
    Features:
    - GPU cards with telemetry
    - Pool badges
    - Temperature graphs
    """
    
    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self._gpu_cards: Dict[int, GpuCard] = {}
        self._build_ui()
    
    def _build_ui(self):
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        self.set_child(main_box)
        
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_box.append(header)
        
        title = Gtk.Label(label="GPUs")
        title.add_css_class("title-2")
        title.set_xalign(0)
        title.set_hexpand(True)
        header.append(title)
        
        # GPU cards container
        self.cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.append(self.cards_box)
        
        # Empty state
        self.empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.empty_box.set_valign(Gtk.Align.CENTER)
        self.empty_box.set_margin_top(48)
        self.empty_box.set_visible(False)
        main_box.append(self.empty_box)
        
        empty_icon = Gtk.Image.new_from_icon_name("video-display-symbolic")
        empty_icon.set_pixel_size(64)
        empty_icon.add_css_class("dim-label")
        self.empty_box.append(empty_icon)
        
        empty_title = Gtk.Label(label="No GPUs Detected")
        empty_title.add_css_class("title-2")
        self.empty_box.append(empty_title)
    
    def update(self, data: dict):
        """Update GPUs from daemon data."""
        gpus = data.get("gpu", data.get("gpus", []))
        
        # Add/update cards
        for i, gpu_data in enumerate(gpus):
            if i not in self._gpu_cards:
                # Create new card
                card = GpuCard(gpu_index=i)
                self._gpu_cards[i] = card
                self.cards_box.append(card)
            
            # Update card
            self._gpu_cards[i].update(gpu_data)
        
        # Remove extra cards
        for i in list(self._gpu_cards.keys()):
            if i >= len(gpus):
                card = self._gpu_cards.pop(i)
                self.cards_box.remove(card)
        
        # Show/hide empty state
        self.empty_box.set_visible(len(gpus) == 0)
