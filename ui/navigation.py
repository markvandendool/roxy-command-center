#!/usr/bin/env python3
"""
Navigation with ViewStack and sidebar.
ROXY-CMD-STORY-007: Application navigation.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Callable


class NavigationSidebar(Gtk.Box):
    """
    Sidebar navigation with icons and labels.
    
    Features:
    - Icon + label navigation buttons
    - Visual selection state
    - Expandable/collapsible
    - Badge support for alerts
    """
    
    def __init__(self, on_navigate: Optional[Callable[[str], None]] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("navigation-sidebar")
        self.set_size_request(200, -1)
        
        self.on_navigate = on_navigate
        self._buttons: Dict[str, Gtk.ToggleButton] = {}
        self._current_page = ""
        
        self._build_ui()
    
    def _build_ui(self):
        # Top section - main navigation
        main_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_section.set_margin_top(8)
        main_section.set_margin_start(8)
        main_section.set_margin_end(8)
        main_section.set_vexpand(True)
        self.append(main_section)
        
        # Navigation items
        nav_items = [
            ("overview", "view-grid-symbolic", "Overview"),
            ("services", "system-run-symbolic", "Services"),
            ("gpus", "video-display-symbolic", "GPUs"),
            ("ollama", "face-smile-big-symbolic", "Ollama"),
            ("alerts", "dialog-warning-symbolic", "Alerts"),
            ("terminal", "utilities-terminal-symbolic", "Terminal"),
        ]
        
        for page_id, icon_name, label in nav_items:
            btn = self._create_nav_button(page_id, icon_name, label)
            main_section.append(btn)
        
        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        main_section.append(sep)
        
        # Settings at bottom
        settings_btn = self._create_nav_button("settings", "emblem-system-symbolic", "Settings")
        main_section.append(settings_btn)
        
        # Footer with version
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        footer.set_margin_bottom(8)
        footer.set_margin_start(12)
        footer.set_margin_end(12)
        self.append(footer)
        
        version = Gtk.Label(label="v1.0.0")
        version.add_css_class("dim-label")
        version.add_css_class("caption")
        version.set_xalign(0)
        footer.append(version)
    
    def _create_nav_button(self, page_id: str, icon_name: str, label: str) -> Gtk.ToggleButton:
        """Create a navigation button."""
        btn = Gtk.ToggleButton()
        btn.add_css_class("nav-button")
        btn.add_css_class("flat")
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn.set_child(box)
        
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(20)
        box.append(icon)
        
        label_widget = Gtk.Label(label=label)
        label_widget.set_xalign(0)
        label_widget.set_hexpand(True)
        box.append(label_widget)
        
        # Store for badge access
        btn._badge_label = None
        
        btn.connect("toggled", self._on_nav_toggled, page_id)
        self._buttons[page_id] = btn
        
        return btn
    
    def _on_nav_toggled(self, button: Gtk.ToggleButton, page_id: str):
        """Handle navigation button toggle."""
        if not button.get_active():
            # If we're deselecting, ignore unless another is selected
            if page_id == self._current_page:
                button.set_active(True)
            return
        
        # Deselect others
        for pid, btn in self._buttons.items():
            if pid != page_id and btn.get_active():
                btn.set_active(False)
        
        self._current_page = page_id
        
        if self.on_navigate:
            self.on_navigate(page_id)
    
    def set_page(self, page_id: str):
        """Programmatically select a page."""
        if page_id in self._buttons:
            self._buttons[page_id].set_active(True)
    
    def set_badge(self, page_id: str, count: int):
        """Set badge count for a page."""
        if page_id not in self._buttons:
            return
        
        btn = self._buttons[page_id]
        box = btn.get_child()
        
        # Find or create badge
        if btn._badge_label is None:
            badge = Gtk.Label()
            badge.add_css_class("nav-badge")
            badge.add_css_class("numeric")
            box.append(badge)
            btn._badge_label = badge
        
        btn._badge_label.set_label(str(count))
        btn._badge_label.set_visible(count > 0)


class NavigationView:
    """
    Navigation view with stack-based pages.
    
    Wraps Adw.NavigationView for modern navigation
    with back button support.
    """
    
    def __init__(self):
        self._widget = Adw.NavigationView()
        self._pages: Dict[str, Adw.NavigationPage] = {}
    
    def get_widget(self):
        return self._widget
    
    def add_page(self, page_id: str, title: str, widget: Gtk.Widget) -> Adw.NavigationPage:
        """Add a page to the navigation view."""
        page = Adw.NavigationPage.new(widget, title)
        page.set_tag(page_id)
        self._pages[page_id] = page
        return page
    
    def navigate_to(self, page_id: str):
        """Navigate to a page by ID."""
        if page_id in self._pages:
            self._widget.push(self._pages[page_id])


class ContentStack(Gtk.Stack):
    """
    Main content area with ViewStack.
    
    Features:
    - Smooth transitions
    - Named pages
    - ViewStack integration
    """
    
    def __init__(self):
        super().__init__()
        self.add_css_class("content-stack")
        
        # Configure transitions
        self.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.set_transition_duration(200)
        
        self._pages: Dict[str, Gtk.Widget] = {}
    
    def add_page(self, page_id: str, title: str, widget: Gtk.Widget,
                 icon_name: str = "") -> Gtk.StackPage:
        """Add a page to the stack."""
        page = self.add_titled(widget, page_id, title)
        if icon_name:
            page.set_icon_name(icon_name)
        self._pages[page_id] = widget
        return page
    
    def navigate_to(self, page_id: str):
        """Navigate to a page."""
        if page_id in self._pages:
            self.set_visible_child_name(page_id)
    
    def get_current_page(self) -> str:
        """Get current page ID."""
        return self.get_visible_child_name() or ""


class MainNavigation(Gtk.Box):
    """
    Combined sidebar + content navigation.
    
    This is the main navigation component that combines
    the sidebar with a content stack.
    """
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add_css_class("main-navigation")
        
        # Sidebar
        self.sidebar = NavigationSidebar(on_navigate=self._on_sidebar_navigate)
        self.append(self.sidebar)
        
        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.append(sep)
        
        # Content stack
        self.stack = ContentStack()
        self.stack.set_hexpand(True)
        self.append(self.stack)
        
        self._page_builders: Dict[str, Callable] = {}
    
    def add_page(self, page_id: str, title: str, widget: Gtk.Widget,
                 icon_name: str = ""):
        """Add a page."""
        self.stack.add_page(page_id, title, widget, icon_name)
    
    def add_lazy_page(self, page_id: str, title: str,
                      builder: Callable[[], Gtk.Widget], icon_name: str = ""):
        """Add a lazily-constructed page."""
        # Add placeholder
        placeholder = Gtk.Box()
        self.stack.add_page(page_id, title, placeholder, icon_name)
        self._page_builders[page_id] = builder
    
    def navigate_to(self, page_id: str):
        """Navigate to a page."""
        # Check if lazy page needs building
        if page_id in self._page_builders:
            builder = self._page_builders.pop(page_id)
            widget = builder()
            
            # Replace placeholder
            placeholder = self.stack._pages.get(page_id)
            if placeholder:
                self.stack.remove(placeholder)
            
            self.stack.add_page(page_id, page_id.title(), widget)
        
        self.stack.navigate_to(page_id)
        self.sidebar.set_page(page_id)
    
    def _on_sidebar_navigate(self, page_id: str):
        """Handle sidebar navigation."""
        self.navigate_to(page_id)
    
    def set_badge(self, page_id: str, count: int):
        """Set badge for a page."""
        self.sidebar.set_badge(page_id, count)
    
    def get_current_page(self) -> str:
        """Get current page ID."""
        return self.stack.get_current_page()
