#!/usr/bin/env python3
"""
Content / Business Page — Content factory queue, social, product.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any


class ContentBusinessPage(Gtk.ScrolledWindow):
    """Content factory and business ops dashboard."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._cards: Dict[str, Gtk.Label] = {}
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        title = Gtk.Label(label="Content & Business")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        # Content factory
        cf_title = Gtk.Label(label="Content Factory")
        cf_title.add_css_class("title-3")
        cf_title.set_xalign(0)
        main_box.append(cf_title)

        cf_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        cf_box.set_homogeneous(True)
        main_box.append(cf_box)

        for key, label in [
            ("queue", "Queue"),
            ("pending", "Pending Posts"),
            ("failed", "Failed Posts"),
            ("published", "Published Today"),
        ]:
            card = self._make_card(label)
            self._cards[key] = card
            cf_box.append(card)

        # Social
        social_title = Gtk.Label(label="Social Command Center")
        social_title.add_css_class("title-3")
        social_title.set_xalign(0)
        social_title.set_margin_top(16)
        main_box.append(social_title)

        social_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        social_box.set_homogeneous(True)
        main_box.append(social_box)

        for key, label in [
            ("youtube", "YouTube"),
            ("instagram", "Instagram"),
            ("tiktok", "TikTok"),
            ("twitter", "X / Twitter"),
        ]:
            card = self._make_card(label)
            self._cards[key] = card
            social_box.append(card)

        # Revenue / Product
        rev_title = Gtk.Label(label="Revenue Radar")
        rev_title.add_css_class("title-3")
        rev_title.set_xalign(0)
        rev_title.set_margin_top(16)
        main_box.append(rev_title)

        rev_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        rev_box.set_homogeneous(True)
        main_box.append(rev_box)

        for key, label in [
            ("products", "Products"),
            ("revenue", "Revenue"),
            ("subscribers", "Subscribers"),
            ("churn", "Churn"),
        ]:
            card = self._make_card(label)
            self._cards[key] = card
            rev_box.append(card)

        # Note
        note = Gtk.Label(label="Content pipeline data will appear here when connected to Skybeam / Social Nucleus.")
        note.add_css_class("dim-label")
        note.set_xalign(0)
        note.set_margin_top(16)
        note.set_wrap(True)
        main_box.append(note)

    def _make_card(self, title: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("overview-card")
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        t = Gtk.Label(label=title)
        t.add_css_class("overview-title")
        t.set_xalign(0)
        box.append(t)

        v = Gtk.Label(label="—")
        v.add_css_class("overview-value")
        v.set_xalign(0)
        box.append(v)

        return box

    def update(self, data: dict):
        # Content factory — not yet piped to apex-status, show placeholder
        for key in ["queue", "pending", "failed", "published"]:
            if key in self._cards:
                box = self._cards[key]
                # Find the value label (second child)
                child = box.get_first_child()
                if child:
                    child = child.get_next_sibling()
                    if child:
                        child.set_label("—")

        # Social — placeholder
        for key in ["youtube", "instagram", "tiktok", "twitter"]:
            if key in self._cards:
                box = self._cards[key]
                child = box.get_first_child()
                if child:
                    child = child.get_next_sibling()
                    if child:
                        child.set_label("—")

        # Revenue — placeholder
        for key in ["products", "revenue", "subscribers", "churn"]:
            if key in self._cards:
                box = self._cards[key]
                child = box.get_first_child()
                if child:
                    child = child.get_next_sibling()
                    if child:
                        child.set_label("—")
