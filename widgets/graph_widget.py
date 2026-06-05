#!/usr/bin/env python3
"""
Graph widget for history visualization.
ROXY-CMD-STORY-012: 60-second history graphs.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import math
from collections import deque
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum


class GraphStyle(Enum):
    LINE = "line"
    FILLED = "filled"
    BAR = "bar"


@dataclass
class GraphConfig:
    """Configuration for a graph."""
    min_value: float = 0.0
    max_value: float = 100.0
    history_seconds: int = 60
    update_interval_ms: int = 1000
    style: GraphStyle = GraphStyle.FILLED
    color: Tuple[float, float, float] = (0.486, 0.227, 0.929)  # Purple
    fill_alpha: float = 0.3
    line_width: float = 2.0
    show_grid: bool = True
    grid_lines: int = 4
    show_current_value: bool = True
    value_format: str = "{:.0f}"
    value_suffix: str = "%"


class GraphWidget(Gtk.DrawingArea):
    """
    Graph widget for displaying time-series data.
    
    Features:
    - 60-second rolling history
    - Line, filled, or bar styles
    - Grid lines
    - Current value overlay
    - Smooth animations
    """
    
    def __init__(self, config: Optional[GraphConfig] = None):
        super().__init__()
        self.config = config or GraphConfig()
        self.add_css_class("graph-widget")
        
        # Calculate data points (one per second for history_seconds)
        self._max_points = self.config.history_seconds
        self._data: deque = deque(maxlen=self._max_points)
        
        # Initialize with zeros
        for _ in range(self._max_points):
            self._data.append(0.0)
        
        # Set minimum size
        self.set_size_request(-1, 80)
        
        # Set up drawing
        self.set_draw_func(self._on_draw)
        
        # Colors from config
        self._line_color = self.config.color
        self._fill_color = (*self.config.color, self.config.fill_alpha)
        self._grid_color = (0.5, 0.5, 0.5, 0.2)
        self._text_color = (0.8, 0.8, 0.8, 1.0)
    
    def add_value(self, value: float):
        """Add a new value to the graph."""
        # Clamp to range
        value = max(self.config.min_value, min(self.config.max_value, value))
        self._data.append(value)
        self.queue_draw()
    
    def set_color(self, r: float, g: float, b: float):
        """Set the graph color."""
        self._line_color = (r, g, b)
        self._fill_color = (r, g, b, self.config.fill_alpha)
        self.queue_draw()
    
    def clear(self):
        """Clear all data."""
        self._data.clear()
        for _ in range(self._max_points):
            self._data.append(0.0)
        self.queue_draw()
    
    def get_current_value(self) -> float:
        """Get the most recent value."""
        return self._data[-1] if self._data else 0.0
    
    def get_average(self) -> float:
        """Get average of all values."""
        if not self._data:
            return 0.0
        return sum(self._data) / len(self._data)
    
    def get_max(self) -> float:
        """Get maximum value."""
        return max(self._data) if self._data else 0.0
    
    def _on_draw(self, area, cr: cairo.Context, width: int, height: int):
        """Draw the graph."""
        if width <= 0 or height <= 0:
            return
        
        # Margins
        margin_left = 8
        margin_right = 8
        margin_top = 8
        margin_bottom = 8
        
        # If showing current value, add more top margin
        if self.config.show_current_value:
            margin_top = 24
        
        # Graph area
        graph_width = width - margin_left - margin_right
        graph_height = height - margin_top - margin_bottom
        
        if graph_width <= 0 or graph_height <= 0:
            return
        
        # Draw grid
        if self.config.show_grid:
            self._draw_grid(cr, margin_left, margin_top, graph_width, graph_height)
        
        # Draw data
        if self.config.style == GraphStyle.BAR:
            self._draw_bars(cr, margin_left, margin_top, graph_width, graph_height)
        else:
            self._draw_line(cr, margin_left, margin_top, graph_width, graph_height)
        
        # Draw current value
        if self.config.show_current_value:
            self._draw_current_value(cr, width, margin_top)
    
    def _draw_grid(self, cr: cairo.Context, x: float, y: float, w: float, h: float):
        """Draw grid lines."""
        cr.set_source_rgba(*self._grid_color)
        cr.set_line_width(1)
        
        # Horizontal lines
        for i in range(self.config.grid_lines + 1):
            line_y = y + (h * i / self.config.grid_lines)
            cr.move_to(x, line_y)
            cr.line_to(x + w, line_y)
            cr.stroke()
        
        # Vertical lines (every 15 seconds)
        intervals = 4  # 60s / 15s
        for i in range(intervals + 1):
            line_x = x + (w * i / intervals)
            cr.move_to(line_x, y)
            cr.line_to(line_x, y + h)
            cr.stroke()
    
    def _draw_line(self, cr: cairo.Context, x: float, y: float, w: float, h: float):
        """Draw line/filled graph."""
        if len(self._data) < 2:
            return
        
        value_range = self.config.max_value - self.config.min_value
        if value_range <= 0:
            return
        
        # Build path
        points: List[Tuple[float, float]] = []
        for i, value in enumerate(self._data):
            px = x + (w * i / (len(self._data) - 1))
            normalized = (value - self.config.min_value) / value_range
            py = y + h - (h * normalized)
            points.append((px, py))
        
        if not points:
            return
        
        # Draw fill first
        if self.config.style == GraphStyle.FILLED:
            cr.move_to(points[0][0], y + h)  # Bottom left
            for px, py in points:
                cr.line_to(px, py)
            cr.line_to(points[-1][0], y + h)  # Bottom right
            cr.close_path()
            
            # Gradient fill
            gradient = cairo.LinearGradient(0, y, 0, y + h)
            gradient.add_color_stop_rgba(0, *self._fill_color)
            gradient.add_color_stop_rgba(1, *self._line_color[:3], 0.05)
            cr.set_source(gradient)
            cr.fill()
        
        # Draw line
        cr.set_source_rgb(*self._line_color)
        cr.set_line_width(self.config.line_width)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        
        cr.move_to(*points[0])
        for px, py in points[1:]:
            cr.line_to(px, py)
        cr.stroke()
        
        # Draw end dot
        last_point = points[-1]
        cr.arc(last_point[0], last_point[1], 3, 0, 2 * math.pi)
        cr.fill()
    
    def _draw_bars(self, cr: cairo.Context, x: float, y: float, w: float, h: float):
        """Draw bar graph."""
        if not self._data:
            return
        
        value_range = self.config.max_value - self.config.min_value
        if value_range <= 0:
            return
        
        bar_width = w / len(self._data)
        gap = 1
        
        for i, value in enumerate(self._data):
            bar_x = x + (bar_width * i) + gap
            normalized = (value - self.config.min_value) / value_range
            bar_height = h * normalized
            bar_y = y + h - bar_height
            
            # Color intensity based on value
            intensity = 0.3 + (0.7 * normalized)
            cr.set_source_rgba(*self._line_color, intensity)
            
            cr.rectangle(bar_x, bar_y, bar_width - (gap * 2), bar_height)
            cr.fill()
    
    def _draw_current_value(self, cr: cairo.Context, width: float, margin_top: float):
        """Draw current value overlay."""
        value = self.get_current_value()
        text = self.config.value_format.format(value) + self.config.value_suffix
        
        cr.set_source_rgba(*self._text_color)
        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(12)
        
        extents = cr.text_extents(text)
        tx = width - extents.width - 8
        ty = margin_top - 6
        
        cr.move_to(tx, ty)
        cr.show_text(text)


class MultiGraphWidget(Gtk.Box):
    """
    Multiple graphs stacked or overlaid.
    
    Features:
    - Multiple data series
    - Legend
    - Synchronized time axis
    """
    
    def __init__(self, series_configs: List[Tuple[str, GraphConfig]]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("multi-graph-widget")
        
        self._graphs: dict = {}
        
        # Legend
        legend = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        legend.set_halign(Gtk.Align.CENTER)
        legend.set_margin_bottom(4)
        self.append(legend)
        
        for name, config in series_configs:
            # Legend item
            item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            legend.append(item)
            
            # Color dot
            dot = Gtk.Label(label="●")
            r, g, b = config.color
            dot.set_markup(f'<span foreground="rgb({int(r*255)},{int(g*255)},{int(b*255)})">●</span>')
            item.append(dot)
            
            label = Gtk.Label(label=name)
            label.add_css_class("caption")
            item.append(label)
        
        # Stacked graphs
        for name, config in series_configs:
            graph = GraphWidget(config)
            graph.set_size_request(-1, 60)
            self._graphs[name] = graph
            self.append(graph)
    
    def add_values(self, values: dict):
        """Add values for multiple series."""
        for name, value in values.items():
            if name in self._graphs:
                self._graphs[name].add_value(value)
    
    def get_graph(self, name: str) -> Optional[GraphWidget]:
        """Get a specific graph by name."""
        return self._graphs.get(name)


class CircularProgressWidget(Gtk.DrawingArea):
    """
    Compact circular progress meter (donut style).
    
    Features:
    - Donut arc with center text + icon
    - Color-coded by severity (green/yellow/red)
    - Compact: ~110x110px vs long bars that eat horizontal real estate
    - Cairo-drawn, no external deps
    """
    
    def __init__(self, size: int = 110, line_width: float = 8.0):
        super().__init__()
        self.add_css_class("circular-progress")
        self.set_size_request(size, size)
        self.set_draw_func(self._on_draw)
        
        self._size = size
        self._line_width = line_width
        self._pct = 0.0
        self._label = ""
        self._subtitle = ""
        self._icon_name = ""
        self._status = "healthy"  # healthy | warn | blocked
    
    def set_value(self, pct: float, label: str = "", subtitle: str = "", icon_name: str = "", status: str = ""):
        """Update meter value and content."""
        self._pct = max(0.0, min(100.0, pct))
        self._label = label
        self._subtitle = subtitle
        self._icon_name = icon_name
        if status in ("healthy", "warn", "blocked"):
            self._status = status
        self.queue_draw()
    
    def _color_for_status(self) -> Tuple[float, float, float]:
        if self._status == "blocked":
            return (0.93, 0.27, 0.27)  # Red
        elif self._status == "warn":
            return (0.96, 0.62, 0.04)  # Orange
        return (0.13, 0.77, 0.37)  # Green
    
    def _on_draw(self, area, cr: cairo.Context, width: int, height: int):
        if width <= 0 or height <= 0:
            return
        
        cx = width / 2.0
        cy = height / 2.0
        radius = min(cx, cy) - self._line_width - 4
        
        # Background track
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source_rgba(0.25, 0.25, 0.25, 0.5)
        cr.set_line_width(self._line_width)
        cr.stroke()
        
        # Progress arc (start at top = -pi/2)
        if self._pct > 0:
            start_angle = -math.pi / 2
            end_angle = start_angle + (2 * math.pi * self._pct / 100.0)
            cr.arc(cx, cy, radius, start_angle, end_angle)
            color = self._color_for_status()
            cr.set_source_rgb(*color)
            cr.set_line_width(self._line_width)
            cr.set_line_cap(cairo.LineCap.ROUND)
            cr.stroke()
        
        # Center text
        cr.set_source_rgb(0.9, 0.9, 0.9)
        
        if self._label:
            # Main label (percentage or value)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(16)
            ext = cr.text_extents(self._label)
            cr.move_to(cx - ext.width / 2, cy - 2)
            cr.show_text(self._label)
        
        if self._subtitle:
            # Subtitle below
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(9)
            cr.set_source_rgb(0.6, 0.6, 0.6)
            ext = cr.text_extents(self._subtitle)
            cr.move_to(cx - ext.width / 2, cy + 14)
            cr.show_text(self._subtitle)


class SparklineWidget(Gtk.DrawingArea):
    """
    Compact sparkline graph for inline display.
    
    Renders external history only. Never fabricates data.
    If history has < 2 real points, renders nothing.
    """
    
    def __init__(self, color: Tuple[float, float, float] = (0.486, 0.227, 0.929)):
        super().__init__()
        self.add_css_class("sparkline")
        self._history: List[float] = []
        self._color = color
        self.set_size_request(80, 24)
        self.set_draw_func(self._on_draw)
    
    def set_history(self, history: List[float]):
        """Set external history. Must be real samples — no synthetic padding."""
        self._history = list(history)
        self.queue_draw()
    
    def _on_draw(self, area, cr: cairo.Context, width: int, height: int):
        """Draw sparkline from real history only."""
        if width <= 0 or height <= 0 or len(self._history) < 2:
            return
        
        margin = 2
        w = width - (margin * 2)
        h = height - (margin * 2)
        
        # Find range
        min_val = min(self._history)
        max_val = max(self._history)
        value_range = max_val - min_val if max_val > min_val else 1
        
        # Build path
        points = []
        n = len(self._history)
        for i, value in enumerate(self._history):
            px = margin + (w * i / (n - 1))
            normalized = (value - min_val) / value_range
            py = margin + h - (h * normalized)
            points.append((px, py))
        
        # Draw fill
        cr.move_to(points[0][0], margin + h)
        for px, py in points:
            cr.line_to(px, py)
        cr.line_to(points[-1][0], margin + h)
        cr.close_path()
        cr.set_source_rgba(*self._color, 0.2)
        cr.fill()
        
        # Draw line
        cr.set_source_rgb(*self._color)
        cr.set_line_width(1.5)
        cr.move_to(*points[0])
        for px, py in points[1:]:
            cr.line_to(px, py)
        cr.stroke()
