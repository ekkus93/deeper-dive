"""TPR-05: an explicit Retry under a saturated worker budget gives visible feedback."""

from __future__ import annotations

from queue import Queue
from threading import Event
from time import monotonic, sleep
from typing import cast

from textual.message import Message

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


def _snapshot() -> FirstRunRuntimeSnapshot:
    return cast(FirstRunRuntimeSnapshot, object())


def test_user_retry_with_saturated_budget_is_visible_and_recovers_when_slot_frees() -> None:
    app = _RecordingApp()
    started = Event()
    release = Event()
    callbacks: list[str] = []

    def blocking_probe() -> FirstRunRuntimeSnapshot:
        started.set()
        assert release.wait(5), "probe release was never signaled"
        return _snapshot()

    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=blocking_probe,
        fingerprint=lambda: "same",
        timeout_seconds=0.05,
        max_workers=1,
    )

    def callback() -> None:
        callbacks.append(coordinator.view.message or coordinator.view.state)

    try:
        assert coordinator.request(app, callback)
        assert started.wait(3)
        app.deliver()  # timeout publication
        assert coordinator.view.state == "failed"
        assert "timed out" in (coordinator.view.message or "").lower()
        timeout_generation = coordinator.view.generation
        callbacks.clear()

        # Automatic refreshes stay quiet: no churn, no callback.
        assert not coordinator.request(app, callback)
        assert coordinator.view.generation == timeout_generation
        assert callbacks == []

        # An explicit Retry must explain why nothing started.
        assert not coordinator.request(app, callback, user_initiated=True)
        assert "still finishing" in (coordinator.view.message or "")
        assert len(callbacks) == 1

        # Once the blocked worker returns, Retry starts a real probe again.
        release.set()
        deadline = monotonic() + 3
        while coordinator.active_worker_count and monotonic() < deadline:
            sleep(0.01)
        assert coordinator.active_worker_count == 0
        started.clear()
        release.clear()
        assert coordinator.request(app, callback, user_initiated=True)
        assert started.wait(3)
    finally:
        release.set()
        coordinator.close()
