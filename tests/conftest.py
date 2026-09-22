"""Shared pytest configuration for Deeper Dive tests."""

from __future__ import annotations

import signal


def _monitor_timeout(signum: int, frame: object) -> None:
    raise TimeoutError("generation monitor responsiveness test exceeded 20 seconds")


def pytest_runtest_setup(item: object) -> None:
    if getattr(item, "name", "") == "test_long_running_fake_provider_does_not_block_tui":
        signal.signal(signal.SIGALRM, _monitor_timeout)
        signal.alarm(20)


def pytest_runtest_teardown(item: object, nextitem: object | None) -> None:
    signal.alarm(0)
