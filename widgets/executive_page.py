#!/usr/bin/env python3
"""
Executive Page — CEO-mode intelligence.
Action ladder, priorities, what failed, what matters.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any, List


class ActionCard(Gtk.Box):
    """Card for an action ladder item."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("overview-card")
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.id_label = Gtk.Label(label="")
        self.id_label.add_css_class("caption")
        self.id_label.set_xalign(0)
        self.append(self.id_label)

        self.title_label = Gtk.Label(label="")
        self.title_label.add_css_class("overview-title")
        self.title_label.set_xalign(0)
        self.title_label.set_wrap(True)
        self.append(self.title_label)

        self.gate_label = Gtk.Label(label="")
        self.gate_label.add_css_class("overview-subtitle")
        self.gate_label.set_xalign(0)
        self.append(self.gate_label)

    def set(self, action_id: str, title: str, cls: str, gate: str):
        self.id_label.set_label(f"{action_id} · {cls}")
        self.title_label.set_label(title)
        self.gate_label.set_label(f"Gate: {gate}")

        self.remove_css_class("status-healthy")
        self.remove_css_class("status-warn")
        self.remove_css_class("status-blocked")
        if gate in ("done", "passed", "green"):
            self.add_css_class("status-healthy")
        elif gate in ("blocked", "red", "failed"):
            self.add_css_class("status-blocked")
        else:
            self.add_css_class("status-warn")


class ExecutivePage(Gtk.ScrolledWindow):
    """CEO-mode dashboard."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._action_cards: List[ActionCard] = []
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        title = Gtk.Label(label="Executive")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        # Sovereign closure summary
        self.closure_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.closure_box.set_margin_bottom(16)
        main_box.append(self.closure_box)

        # Action ladder
        ladder_title = Gtk.Label(label="Action Ladder")
        ladder_title.add_css_class("title-3")
        ladder_title.set_xalign(0)
        main_box.append(ladder_title)

        self.ladder_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.append(self.ladder_box)

        # Next action
        self.next_label = Gtk.Label(label="")
        self.next_label.add_css_class("caption")
        self.next_label.set_xalign(0)
        self.next_label.set_margin_top(16)
        main_box.append(self.next_label)

    def update(self, data: dict):
        # Sovereign closure
        while self.closure_box.get_first_child():
            self.closure_box.remove(self.closure_box.get_first_child())

        closure = data.get("sovereignClosure", {})
        if closure:
            status = closure.get("status", "?")
            lbl = Gtk.Label(label=f"Sovereign Closure: {status.upper()}")
            lbl.add_css_class("title-3")
            lbl.set_xalign(0)
            self.closure_box.append(lbl)

            metrics = [
                ("Authority Convergence", closure.get("authorityConvergence", "?")),
                ("Proof Coverage", closure.get("proofCoverage", "?")),
                ("Discovery Debt", closure.get("discoveryDebt", "?")),
                ("Campaigns", f"{closure.get('campaignsConverged', 0)}/{closure.get('campaignsTotal', 0)}"),
            ]
            for name, val in metrics:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                n = Gtk.Label(label=name)
                n.set_hexpand(True)
                n.set_xalign(0)
                v = Gtk.Label(label=str(val))
                v.add_css_class("monospace")
                v.set_xalign(1)
                row.append(n)
                row.append(v)
                self.closure_box.append(row)

        # Action ladder
        ladder = data.get("actionLadderSummary", [])
        # Clear old cards if count changed significantly
        if len(ladder) != len(self._action_cards):
            while self.ladder_box.get_first_child():
                self.ladder_box.remove(self.ladder_box.get_first_child())
            self._action_cards = []
            for item in ladder:
                card = ActionCard()
                self._action_cards.append(card)
                self.ladder_box.append(card)

        for i, item in enumerate(ladder):
            if i < len(self._action_cards):
                self._action_cards[i].set(
                    item.get("id", "?"),
                    item.get("title", "?"),
                    item.get("class", "?"),
                    item.get("gate", "?"),
                )

        # Next action
        next_action = data.get("nextAction", "")
        self.next_label.set_label(f"Next: {next_action}")
