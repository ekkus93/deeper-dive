"""Additional deterministic first-run readiness publication regressions."""

from __future__ import annotations

from queue import Queue
from threading import Event
from typing import cast

from textual.message import Message

from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunReadinessDispatch,
    FirstRunRuntimeSnapshot,
)
from deeper_dive.guided_workflow import WizardContext


class _App:
    def __init__(self) -> None:
        self.messages: Queue[Message] = Queue()

    def post_message(self, message: Message) -> bool:
        self.messages.put(message)
        return True

    def deliver(self) -> None:
        message = self.messages.get(timeout=3)
        assert isinstance(message, FirstRunReadinessDispatch)
        message.run()


def _context() -> WizardContext:
    return cast(WizardContext, object())


def _snapshot() -> FirstRunRuntimeSnapshot:
    return cast(FirstRunRuntimeSnapshot, object())


def test_probe_failure_publishes_once_without_duplicate_callbacks() -> None:
    app = _App()
    callbacks: list[str] = []

    def fail() -> FirstRunRuntimeSnapshot:
        raise RuntimeError("deterministic provider unavailable")

    coordinator = FirstRunReadinessCoordinator(
        _context(), probe=fail, fingerprint=lambda: "failed", timeout_seconds=5
    )
    try:
        assert coordinator.request(app, lambda: callbacks.append("failed"))
        app.deliver()
        assert coordinator.view.state == "failed"
        assert "provider unavailable" in (coordinator.view.message or "")
        assert callbacks == ["failed"]
    finally:
        coordinator.close()


def test_superseded_probe_result_cannot_overwrite_newer_snapshot() -> None:
    app = _App()
    old_started = Event()
    release_old = Event()
    fingerprint = ["old"]
    callbacks: list[str] = []
    old_snapshot = _snapshot()
    new_snapshot = _snapshot()

    def probe() -> FirstRunRuntimeSnapshot:
        if fingerprint[0] == "old":
            old_started.set()
            assert release_old.wait(3)
            return old_snapshot
        return new_snapshot

    coordinator = FirstRunReadinessCoordinator(
        _context(), probe=probe, fingerprint=lambda: fingerprint[0], timeout_seconds=5
    )
    try:
        assert coordinator.request(app, lambda: callbacks.append("old"))
        assert old_started.wait(3)
        fingerprint[0] = "new"
        assert coordinator.request(app, lambda: callbacks.append("new"))
        app.deliver()
        assert coordinator.view.state == "ready"
        assert coordinator.snapshot is new_snapshot
        release_old.set()
        app.deliver()
        assert coordinator.snapshot is new_snapshot
        assert callbacks == ["new"]
    finally:
        release_old.set()
        coordinator.close()
