"""Shutdown regressions for readiness dispatch when the UI message pump closes."""

from __future__ import annotations

from threading import Event
from time import monotonic, sleep
from typing import cast

from textual.message import Message

from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunRuntimeSnapshot,
)
from deeper_dive.guided_workflow import WizardContext


class _ClosedMessagePump:
    def __init__(self) -> None:
        self.rejected = Event()
        self.messages: list[Message] = []

    def post_message(self, message: Message) -> bool:
        self.messages.append(message)
        self.rejected.set()
        return False


def _wait_for_release(coordinator: FirstRunReadinessCoordinator) -> None:
    deadline = monotonic() + 3
    while coordinator.active_worker_count and monotonic() < deadline:
        sleep(0.001)
    assert coordinator.active_worker_count == 0


def test_rejected_probe_completion_closes_coordinator_without_callback() -> None:
    app = _ClosedMessagePump()
    callbacks: list[str] = []
    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=lambda: cast(FirstRunRuntimeSnapshot, object()),
        fingerprint=lambda: "closed",
        timeout_seconds=5,
    )
    try:
        assert coordinator.request(app, lambda: callbacks.append("unexpected"))
        assert app.rejected.wait(3)
        _wait_for_release(coordinator)
        assert coordinator.timeout_timer_count == 0
        assert coordinator.view.state == "failed"
        assert callbacks == []
        assert not coordinator.request(app)
    finally:
        coordinator.close()


def test_rejected_timeout_closes_coordinator_with_blocked_probe() -> None:
    app = _ClosedMessagePump()
    release = Event()
    started = Event()
    callbacks: list[str] = []

    def blocked_probe() -> FirstRunRuntimeSnapshot:
        started.set()
        assert release.wait(3)
        return cast(FirstRunRuntimeSnapshot, object())

    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=blocked_probe,
        fingerprint=lambda: "closed",
        timeout_seconds=0.02,
    )
    try:
        assert coordinator.request(app, lambda: callbacks.append("unexpected"))
        assert started.wait(3)
        assert app.rejected.wait(3)
        deadline = monotonic() + 3
        while coordinator.timeout_timer_count and monotonic() < deadline:
            sleep(0.001)
        assert coordinator.timeout_timer_count == 0
        assert coordinator.view.state == "failed"
        assert callbacks == []
        assert not coordinator.request(app)
        release.set()
        _wait_for_release(coordinator)
    finally:
        release.set()
        coordinator.close()
