#!/usr/bin/env python3
"""
TruthBadge — reusable GTK badge for factory/route/memory truth.

Enforces the green-state gate: a PASS/green badge MUST carry provenance
(source, command, timestamp, receiptPath). If provenance is missing, the
badge renders DEGRADED even if the caller asked for PASS.

States: PASS, DEGRADED, FAIL, OFF, OPTIONAL, LOADING, UNPROVEN.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk
from typing import Dict, Any, Optional


STATE_COLORS = {
    "PASS": "#35d07f",
    "DEGRADED": "#f5b64a",
    "FAIL": "#f06464",
    "OFF": "#8fa0b5",
    "OPTIONAL": "#b18cff",
    "LOADING": "#4fd6ff",
    "UNPROVEN": "#8fa0b5",
}

STATE_BG_ALPHA = {
    "PASS": "rgba(53, 208, 127, 0.12)",
    "DEGRADED": "rgba(245, 182, 74, 0.15)",
    "FAIL": "rgba(240, 100, 100, 0.15)",
    "OFF": "rgba(143, 160, 181, 0.10)",
    "OPTIONAL": "rgba(177, 140, 255, 0.12)",
    "LOADING": "rgba(79, 214, 255, 0.12)",
    "UNPROVEN": "rgba(143, 160, 181, 0.10)",
}

REQUIRED_PROVENANCE = {"source", "command", "timestamp", "receiptPath"}


def _state_from_value(value: str) -> str:
    v = str(value).upper()
    if v in ("PASS", "OK", "READY", "HEALTHY", "GREEN", "TRUE"):
        return "PASS"
    if v in ("DEGRADED", "WARN", "YELLOW", "STALE"):
        return "DEGRADED"
    if v in ("FAIL", "ERROR", "RED", "UNHEALTHY", "FALSE"):
        return "FAIL"
    if v in ("OFF", "DISABLED", "DOWN"):
        return "OFF"
    if v in ("OPTIONAL"):
        return "OPTIONAL"
    if v in ("LOADING"):
        return "LOADING"
    return "UNPROVEN"


class TruthBadge(Gtk.Box):
    """A badge that refuses to show green without provenance."""

    def __init__(self, label: str = "", state: str = "UNPROVEN",
                 provenance: Optional[Dict[str, Any]] = None,
                 detail: str = ""):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.add_css_class("truth-badge")
        self.set_margin_top(1)
        self.set_margin_bottom(1)

        self._provenance: Dict[str, Any] = dict(provenance or {})
        self._detail = detail

        self._dot = Gtk.Label(label="●")
        self._dot.set_markup("<span color='#8fa0b5'>●</span>")
        self.append(self._dot)

        self._label = Gtk.Label(label=label or "--")
        self._label.add_css_class("caption")
        self._label.set_xalign(0)
        self.append(self._label)

        self._tooltip = Gtk.EventControllerMotion()
        self._tooltip.connect("enter", self._on_hover)
        self.add_controller(self._tooltip)

        self.set_truth(state, provenance, detail)

    def set_truth(self, value: str, provenance: Optional[Dict[str, Any]] = None,
                  detail: str = ""):
        """Set badge state and enforce green-state gate."""
        state = _state_from_value(value)
        self._provenance = dict(provenance or self._provenance)
        self._detail = detail or self._detail

        # Green-state gate: PASS requires provenance
        if state == "PASS" and not self._has_provenance():
            state = "DEGRADED"
            self._detail = (self._detail + "; provenance missing" if self._detail else "provenance missing")

        self._state = state
        color = STATE_COLORS.get(state, STATE_COLORS["UNPROVEN"])
        bg = STATE_BG_ALPHA.get(state, STATE_BG_ALPHA["UNPROVEN"])

        self._dot.set_markup(f'<span color="{color}">●</span>')
        self._label.set_label(self._label.get_label())

        # Inline style for background
        self.set_css_name("box")
        self._apply_style(bg, color)

    @property
    def state(self) -> str:
        return self._state

    def _has_provenance(self) -> bool:
        return bool(self._provenance) and REQUIRED_PROVENANCE.issubset(self._provenance.keys())

    def _apply_style(self, bg: str, fg: str):
        css = f"""
        .truth-badge {{
            background-color: {bg};
            color: {fg};
            border-radius: 4px;
            padding: 1px 6px;
        }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        style = self.get_style_context()
        style.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _on_hover(self, controller, x, y):
        parts = [f"State: {self._state}"]
        if self._detail:
            parts.append(f"Detail: {self._detail}")
        if self._provenance:
            parts.append(f"Source: {self._provenance.get('source', '?')}")
            parts.append(f"Command: {self._provenance.get('command', '?')}")
            parts.append(f"Generated: {self._provenance.get('timestamp', '?')}")
            parts.append(f"Receipt: {self._provenance.get('receiptPath', 'none')}")
            if self._provenance.get("stale"):
                parts.append("STALE: using last good snapshot")
        self.set_tooltip_text("\n".join(parts))

    def get_state(self) -> str:
        return getattr(self, "_state", "UNPROVEN")

    def get_provenance(self) -> Dict[str, Any]:
        return dict(self._provenance)


class TruthBadgeGroup(Gtk.Box):
    """Horizontal group of TruthBadges with consistent spacing."""

    def __init__(self, spacing: int = 6):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)
        self._badges: Dict[str, TruthBadge] = {}

    def set_badge(self, key: str, label: str, value: str,
                  provenance: Optional[Dict[str, Any]] = None, detail: str = ""):
        if key not in self._badges:
            badge = TruthBadge(label, value, provenance, detail)
            self._badges[key] = badge
            self.append(badge)
        else:
            self._badges[key].set_truth(value, provenance, detail)

    def get_badge(self, key: str) -> Optional[TruthBadge]:
        return self._badges.get(key)
