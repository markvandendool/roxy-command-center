#!/usr/bin/env python3
"""Focused coverage for native page update exception isolation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import run_surface_update


def test_failure_is_visible_and_does_not_abort_next_surface():
    calls = []
    errors = []

    def broken(_data):
        calls.append("broken")
        raise TypeError("bad card payload")

    def healthy(data):
        calls.append(data["marker"])

    assert not run_surface_update("overview", broken, {"marker": "healthy"}, errors.append)
    assert run_surface_update("services", healthy, {"marker": "healthy"}, errors.append)

    assert calls == ["broken", "healthy"]
    assert len(errors) == 1
    assert errors[0]["code"] == "RCC_SURFACE_UPDATE_FAILED"
    assert errors[0]["surfaceId"] == "overview"
    assert errors[0]["evaluatedExpression"] == "overview.update(data)"
    assert errors[0]["exceptionName"] == "TypeError"
    assert errors[0]["message"] == "bad card payload"
    assert "TypeError: bad card payload" in errors[0]["stack"]


def main() -> int:
    test_failure_is_visible_and_does_not_abort_next_surface()
    print("RCC_SURFACE_UPDATE_ISOLATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
