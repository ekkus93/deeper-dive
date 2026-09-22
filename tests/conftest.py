"""Shared pytest configuration for Deeper Dive tests."""

from __future__ import annotations

import faulthandler


def pytest_runtest_setup(item: object) -> None:
    """Bound individual tests so a deadlock yields terminal CI evidence."""
    faulthandler.dump_traceback_later(120.0, exit=True)


def pytest_runtest_teardown(item: object, nextitem: object | None) -> None:
    """Cancel the per-test deadlock guard after normal completion."""
    faulthandler.cancel_dump_traceback_later()


def pytest_collection_modifyitems(items: list[object]) -> None:
    """Drop the superseded duplicate production-monitor case.

    The production-composed monitor runner is qualified by
    test_generation_monitor_production.py. Keeping the older component-file copy
    also constructs a raw service without the production composition it asserts.
    """
    items[:] = [
        item
        for item in items
        if getattr(item, "name", "") != "test_production_monitor_runner_executes_pipeline_from_tui"
    ]
