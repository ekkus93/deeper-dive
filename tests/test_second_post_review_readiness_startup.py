"""Regression tests for readiness thread-start failure and recovery."""

from __future__ import annotations

from threading import Event, Thread, Timer
from typing import cast

import pytest
from textual.message import Message

from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunReadinessDispatch,
    FirstRunRuntimeSnapshot,
)
from deeper_dive.guided_workflow import WizardContext


class _App:
    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.arrived = Event()

    def post_message(self, message: Message) -> bool:
        self.messages.append(message)
        self.arrived.set()
        return True


@pytest.mark.parametrize("failed_start", ["timer", "worker"])
def test_failed_thread_start_releases_slot_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch, failed_start: str
) -> None:
    app = _App()
    callbacks: list[str] = []
    original_start = Thread.start

    def fail_start(thread: Thread) -> None:
        is_timer = isinstance(thread, Timer)
        if (failed_start == "timer" and is_timer) or (
            failed_start == "worker" and thread.name.startswith("deeper-dive-readiness-")
        ):
            raise RuntimeError("synthetic startup failure")
        original_start(thread)

    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=lambda: cast(FirstRunRuntimeSnapshot, object()),
        fingerprint=lambda: "same",
        timeout_seconds=3,
        max_workers=1,
    )
    try:
        monkeypatch.setattr(Thread, "start", fail_start)
        assert not coordinator.request(app, lambda: callbacks.append(coordinator.view.state))
        assert callbacks == ["failed"]
        assert coordinator.view.state == "failed"
        assert "Retry" in (coordinator.view.message or "")
        assert coordinator.active_worker_count == 0
        assert coordinator.timeout_timer_count == 0
        assert coordinator.queued_worker_count == 0
        assert not app.messages

        monkeypatch.undo()
        assert coordinator.request(app, lambda: callbacks.append(coordinator.view.state))
        assert app.arrived.wait(3)
        assert len(app.messages) == 1
        dispatch = app.messages.pop()
        assert isinstance(dispatch, FirstRunReadinessDispatch)
        dispatch.run()
        assert callbacks == ["failed", "ready"]
        assert coordinator.view.state == "ready"
        assert coordinator.timeout_timer_count == 0
    finally:
        monkeypatch.undo()
        coordinator.close()


def test_provider_probe_exception_is_sanitized_and_retryable() -> None:
    """An isolated provider failure reports once without publishing credentials."""
    app = _App()
    callbacks: list[str] = []
    repaired = [False]

    def probe() -> FirstRunRuntimeSnapshot:
        if not repaired[0]:
            raise ValueError("api_key=synthetic-probe-secret")
        return cast(FirstRunRuntimeSnapshot, object())

    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=probe,
        fingerprint=lambda: "unchanged",
        timeout_seconds=3,
    )
    try:
        assert coordinator.request(app, lambda: callbacks.append(coordinator.view.state))
        assert app.arrived.wait(3)
        dispatch = app.messages.pop()
        assert isinstance(dispatch, FirstRunReadinessDispatch)
        dispatch.run()
        assert coordinator.view.state == "failed"
        assert "synthetic-probe-secret" not in (coordinator.view.message or "")
        assert "[REDACTED]" in (coordinator.view.message or "")
        assert callbacks == ["failed"]
        assert coordinator.timeout_timer_count == 0

        app.arrived.clear()
        repaired[0] = True
        assert coordinator.request(app, lambda: callbacks.append(coordinator.view.state))
        assert app.arrived.wait(3)
        dispatch = app.messages.pop()
        assert isinstance(dispatch, FirstRunReadinessDispatch)
        dispatch.run()
        assert coordinator.view.state == "ready"
        assert callbacks == ["failed", "ready"]
        assert coordinator.timeout_timer_count == 0
    finally:
        coordinator.close()
