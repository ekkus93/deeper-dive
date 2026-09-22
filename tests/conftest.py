"""Shared test guards for deterministic CI execution."""

from __future__ import annotations

import faulthandler


def pytest_runtest_setup(item: object) -> None:
    """Bound every test so a deadlock produces actionable CI evidence."""
    faulthandler.dump_traceback_later(20.0, exit=True)


def pytest_runtest_teardown(item: object, nextitem: object | None) -> None:
    """Cancel the per-test deadlock guard after normal completion."""
    faulthandler.cancel_dump_traceback_later()
