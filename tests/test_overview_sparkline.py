#!/usr/bin/env python3
"""Focused tests for Overview-owned bounded sparkline history."""

import math
import sys
from pathlib import Path
from unittest.mock import patch

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

sys.path.insert(0, str(Path(__file__).parent.parent))

from widgets.graph_widget import SparklineWidget
from widgets.overview_page import OverviewCard


def test_append_trim_and_redraw():
    card = OverviewCard("CPU", show_sparkline=True)

    with patch.object(SparklineWidget, "queue_draw") as queue_draw:
        for value in range(35):
            assert card.add_sparkline_value(value)

    expected = [float(value) for value in range(5, 35)]
    assert list(card._sparkline_history) == expected
    assert card._sparkline._history == expected
    assert queue_draw.call_count == 35


def test_invalid_values_degrade_without_mutating_history():
    card = OverviewCard("Memory", show_sparkline=True)
    assert card.add_sparkline_value(42)
    expected = [42.0]

    for value in (None, "not-a-number", math.nan, math.inf, -math.inf):
        assert not card.add_sparkline_value(value)
        assert list(card._sparkline_history) == expected
        assert card._sparkline._history == expected
        assert card._sparkline_error.get_visible()

    assert card.add_sparkline_value(43)
    assert list(card._sparkline_history) == [42.0, 43.0]
    assert not card._sparkline_error.get_visible()


def test_non_sparkline_card_rejects_samples_safely():
    card = OverviewCard("Law 0")
    assert not card.add_sparkline_value(1)


def main() -> int:
    Gtk.init()
    test_append_trim_and_redraw()
    test_invalid_values_degrade_without_mutating_history()
    test_non_sparkline_card_rejects_samples_safely()
    print("RCC_OVERVIEW_SPARKLINE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
