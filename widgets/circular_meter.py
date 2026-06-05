#!/usr/bin/env python3
"""Compact circular meter for bounded command-center metrics."""

import math

import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk


class CircularMeter(Gtk.DrawingArea):
    """A compact ring meter with central percent text."""

    COLORS = {
        "healthy": (0.21, 0.82, 0.50),
        "warn": (0.96, 0.71, 0.29),
        "blocked": (0.94, 0.35, 0.35),
        "info": (0.31, 0.84, 1.0),
    }

    def __init__(self, size: int = 118):
        super().__init__()
        self.set_size_request(size, size)
        self._percent = 0.0
        self._center_text = "--"
        self._caption = ""
        self._status = "info"
        self.set_draw_func(self._on_draw)

    def set_value(self, percent: float, center_text: str = "", caption: str = "", status: str = "info"):
        self._percent = max(0.0, min(100.0, float(percent or 0)))
        self._center_text = center_text or f"{self._percent:.0f}%"
        self._caption = caption
        self._status = status if status in self.COLORS else "info"
        self.queue_draw()

    def _on_draw(self, area, cr: cairo.Context, width: int, height: int):
        if width <= 0 or height <= 0:
            return

        cx = width / 2
        cy = height / 2
        radius = min(width, height) / 2 - 11
        start = -math.pi / 2
        end = start + (2 * math.pi * self._percent / 100.0)
        color = self.COLORS.get(self._status, self.COLORS["info"])

        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(9)

        cr.set_source_rgba(0.18, 0.24, 0.32, 0.85)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        cr.set_source_rgb(*color)
        cr.arc(cx, cy, radius, start, end)
        cr.stroke()

        cr.set_source_rgba(*color, 0.10)
        cr.arc(cx, cy, radius - 8, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgb(0.96, 0.98, 1.0)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(24)
        ext = cr.text_extents(self._center_text)
        cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy - 2 - ext.height / 2 - ext.y_bearing)
        cr.show_text(self._center_text)

        if self._caption:
            cr.set_source_rgb(0.56, 0.63, 0.71)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(10)
            ext = cr.text_extents(self._caption)
            cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy + 23 - ext.height / 2 - ext.y_bearing)
            cr.show_text(self._caption)
