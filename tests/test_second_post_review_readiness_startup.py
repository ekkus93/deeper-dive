"""Regression tests for readiness thread-start failure and recovery."""

from __future__ import annotations

from threading import Thread, Timer
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

    def post_message(self, message: Message) -> bool:
        self.messages.append(message)
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
        for _ in range(1000):
            if app.messages:
                break
            from time import sleep
            sleep(0.001)
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
