"""Shared pytest configuration for Deeper Dive tests."""

from __future__ import annotations

import faulthandler


def pytest_runtest_setup(item: object) -> None:
    """Bound individual tests so a deadlock yields terminal CI evidence."""
    faulthandler.dump_traceback_later(120.0, exit=True)


def pytest_runtest_teardown(item: object, nextitem: object | None) -> None:
    """Cancel the per-test deadlock guard after normal completion."""
    faulthandler.cancel_dump_traceback_later()
