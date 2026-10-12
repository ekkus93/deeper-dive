"""Type errors from malformed readiness fingerprints must remain recoverable."""

from __future__ import annotations

from queue import Queue
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


def test_initial_fingerprint_type_error_fails_actionably_then_recovers() -> None:
    app = _RecordingApp()
    repaired = [False]
    callbacks: list[str] = []

    def fingerprint() -> str:
        if not repaired[0]:
            raise TypeError("invalid configuration fingerprint")
        return "repaired"

    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=lambda: cast(FirstRunRuntimeSnapshot, object()),
        fingerprint=fingerprint,
        timeout_seconds=3,
    )
    try:
        assert not coordinator.request(app, lambda: callbacks.append(coordinator.view.state))
        assert coordinator.view.state == "failed"
        assert "Correct the configuration and retry." in (coordinator.view.message or "")
        assert callbacks == ["failed"]
        assert coordinator.active_worker_count == 0
        assert coordinator.timeout_timer_count == 0

        repaired[0] = True
        assert coordinator.request(app, lambda: callbacks.append(coordinator.view.state))
        app.deliver()
        assert coordinator.view.state == "ready"
        assert callbacks == ["failed", "ready"]
        assert coordinator.timeout_timer_count == 0
    finally:
        coordinator.close()


def test_completion_fingerprint_type_error_cannot_escape_ui_dispatch() -> None:
    app = _RecordingApp()
    reads = [0]
    callbacks: list[str] = []

    def fingerprint() -> str:
        reads[0] += 1
        if reads[0] > 1:
            raise TypeError("configuration changed shape")
        return "initial"

    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=lambda: cast(FirstRunRuntimeSnapshot, object()),
        fingerprint=fingerprint,
        timeout_seconds=3,
    )
    try:
        assert coordinator.request(app, lambda: callbacks.append(coordinator.view.state))
        app.deliver()
        assert coordinator.view.state == "failed"
        assert "Correct the configuration and retry." in (coordinator.view.message or "")
        assert callbacks == ["failed"]
        assert coordinator.snapshot is None
        assert coordinator.timeout_timer_count == 0
    finally:
        coordinator.close()
