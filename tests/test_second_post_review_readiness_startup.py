"""Regression matrix for readiness worker/timer startup failures."""

from __future__ import annotations

from queue import Queue
from typing import cast

import pytest
from textual.message import Message

import deeper_dive.guided_async_readiness as readiness
from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunReadinessDispatch,
    FirstRunRuntimeSnapshot,
)
from deeper_dive.guided_workflow import WizardContext


class _RecordingApp:
    def __init__(self) -> None:
        self.messages: Queue[Message] = Queue()

    def post_message(self, message: Message) -> bool:
        self.messages.put(message)
        return True

    def deliver(self) -> None:
        message = self.messages.get(timeout=3)
        assert isinstance(message, FirstRunReadinessDispatch)
        message.run()


@pytest.mark.parametrize("stage", ["timer", "worker"])
@pytest.mark.parametrize("failure_type", [RuntimeError, OSError])
def test_startup_failure_releases_capacity_notifies_once_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    failure_type: type[Exception],
) -> None:
    app = _RecordingApp()
    callbacks: list[str] = []
    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=lambda: cast(FirstRunRuntimeSnapshot, object()),
        fingerprint=lambda: "same",
        timeout_seconds=5,
        max_workers=1,
    )

    def reject_start(self: object) -> None:
        raise failure_type("simulated readiness thread startup failure")

    class FailingWorker:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def start(self) -> None:
            reject_start(self)

    try:
        with monkeypatch.context() as patcher:
            if stage == "timer":
                patcher.setattr(readiness.Timer, "start", reject_start)
            else:
                patcher.setattr(readiness, "Thread", FailingWorker)
            assert not coordinator.request(app, lambda: callbacks.append(coordinator.view.state))
        assert coordinator.view.state == "failed"
        assert coordinator.view.message == "Unable to start provider readiness check. Retry."
        assert callbacks == ["failed"]
        assert coordinator.active_worker_count == 0
        assert coordinator.timeout_timer_count == 0
        assert app.messages.empty()

        assert coordinator.request(app, lambda: callbacks.append(coordinator.view.state))
        app.deliver()
        assert coordinator.view.state == "ready"
        assert callbacks == ["failed", "ready"]
        assert coordinator.timeout_timer_count == 0
    finally:
        coordinator.close()
