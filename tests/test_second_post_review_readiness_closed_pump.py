"""A closed Textual message pump may raise instead of returning False."""

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


class RaisingApp:
    def post_message(self, message: Message) -> bool:
        raise RuntimeError("closed message pump")


def test_readiness_dispatch_treats_closed_pump_exception_as_rejection() -> None:
    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        fingerprint=lambda: "test",
    )
    try:
        assert not coordinator._dispatch(RaisingApp(), lambda: None)
    finally:
        coordinator.close()


def test_worker_completion_closes_coordinator_when_pump_raises() -> None:
    posted = Event()
    callbacks: list[str] = []

    class App:
        def post_message(self, message: Message) -> bool:
            posted.set()
            raise RuntimeError("closed message pump")

    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        probe=lambda: cast(FirstRunRuntimeSnapshot, object()),
        fingerprint=lambda: "closed",
        timeout_seconds=5,
    )
    try:
        assert coordinator.request(App(), lambda: callbacks.append("unexpected"))
        assert posted.wait(3)
        deadline = monotonic() + 3
        while coordinator.active_worker_count and monotonic() < deadline:
            sleep(0.001)
        assert coordinator.active_worker_count == 0
        assert coordinator.timeout_timer_count == 0
        assert coordinator.view.state == "failed"
        assert callbacks == []
        assert not coordinator.request(App())
    finally:
        coordinator.close()
