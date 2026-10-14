"""TPR-14: readiness subscribers survive supersession and are isolated from each other."""

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

    def deliver_all_until(self, done: Event) -> None:
        while not done.is_set():
            message = self.messages.get(timeout=5)
            assert isinstance(message, FirstRunReadinessDispatch)
            message.run()


def _coordinator(fingerprints: list[str], release: Event) -> FirstRunReadinessCoordinator:
    def probe() -> FirstRunRuntimeSnapshot:
        assert release.wait(5)
        return cast(FirstRunRuntimeSnapshot, object())

    return FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=probe,
        fingerprint=lambda: fingerprints[-1],
        timeout_seconds=5,
        max_workers=4,
    )


def test_subscriber_of_superseded_generation_is_notified_once() -> None:
    app = _App()
    release = Event()
    fingerprints = ["one"]
    coordinator = _coordinator(fingerprints, release)
    calls: list[str] = []
    done = Event()
    try:
        assert coordinator.request(app, lambda: calls.append("a"))
        fingerprints.append("two")  # configuration changed: supersede generation 1
        assert coordinator.request(
            app,
            lambda: (calls.append("b"), done.set()),
        )
        release.set()
        # Deliver results until generation 2 publishes.
        while not done.is_set():
            message = app.messages.get(timeout=5)
            assert isinstance(message, FirstRunReadinessDispatch)
            message.run()
        assert sorted(calls) == ["a", "b"]
    finally:
        release.set()
        coordinator.close()


def test_raising_subscriber_does_not_block_later_subscribers() -> None:
    app = _App()
    release = Event()
    coordinator = _coordinator(["same"], release)
    calls: list[str] = []
    done = Event()

    def boom() -> None:
        raise RuntimeError("secret sk-abcdefghijklmnopqrstuvwxyz123456")

    try:
        assert coordinator.request(app, boom)
        assert not coordinator.request(app, lambda: calls.append("second"))
        assert not coordinator.request(app, lambda: (calls.append("third"), done.set()))
        release.set()
        app.deliver_all_until(done)
        assert calls == ["second", "third"]
    finally:
        release.set()
        coordinator.close()
