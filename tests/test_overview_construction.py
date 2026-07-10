#!/usr/bin/env python3
"""Regression coverage for the native Overview construction path."""

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

sys.path.insert(0, str(Path(__file__).parent.parent))

from widgets.overview_page import OverviewCard, OverviewPage


def test_sparkline_card_constructs():
    card = OverviewCard("CPU", show_sparkline=True)
    assert card._sparkline is not None


def test_overview_page_constructs_with_sparklines():
    page = OverviewPage()
    for card_id in ("cpu", "cpu_idle", "memory", "gpu0", "gpu1"):
        assert page._cards[card_id]._sparkline is not None


def main() -> int:
    Gtk.init()
    test_sparkline_card_constructs()
    test_overview_page_constructs_with_sparklines()
    print("RCC_OVERVIEW_CONSTRUCTION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
