"""Deterministic readiness worker-budget and callback coalescing regressions."""

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


def _context() -> WizardContext:
    # A supplied deterministic probe/fingerprint does not inspect context.
    return cast(WizardContext, object())


def _snapshot() -> FirstRunRuntimeSnapshot:
    # Only publication identity matters in this worker-budget test.
    return cast(FirstRunRuntimeSnapshot, object())


def test_hundred_identical_refreshes_coalesce_probe_and_callback() -> None:
    app = _RecordingApp()
    started = Event()
    release = Event()
    probes: list[int] = []
    callbacks: list[int] = []

    def blocking_probe() -> FirstRunRuntimeSnapshot:
        probes.append(1)
        started.set()
        assert release.wait(3), "probe release was never signaled"
        return _snapshot()

    coordinator = FirstRunReadinessCoordinator(
        _context(), probe=blocking_probe, fingerprint=lambda: "same", timeout_seconds=5
    )

    def callback() -> None:
        callbacks.append(1)

    try:
        assert coordinator.request(app, callback)
        assert started.wait(3)
        for _ in range(100):
            assert not coordinator.request(app, callback)
        assert probes == [1]
        assert coordinator.active_worker_count == 1
        assert coordinator.queued_worker_count == 0
        assert coordinator.timeout_timer_count == 1
        release.set()
        app.deliver()
        assert callbacks == [1]
        assert coordinator.view.state == "ready"
    finally:
        release.set()
        coordinator.close()


def test_timed_out_probe_never_publishes_late_success_or_duplicate_callback() -> None:
    app = _RecordingApp()
    started = Event()
    release = Event()
    callbacks: list[str] = []

    def blocking_probe() -> FirstRunRuntimeSnapshot:
        started.set()
        assert release.wait(3), "probe release was never signaled"
        return _snapshot()

    coordinator = FirstRunReadinessCoordinator(
        _context(), probe=blocking_probe, fingerprint=lambda: "same", timeout_seconds=0.05
    )

    def callback() -> None:
        callbacks.append(coordinator.view.state)

    try:
        assert coordinator.request(app, callback)
        assert started.wait(3)
        for _ in range(20):
            assert not coordinator.request(app, callback)
        app.deliver()
        assert callbacks == ["failed"]
        assert coordinator.view.state == "failed"
        assert coordinator.active_worker_count == 1
        release.set()
        app.deliver()
        assert coordinator.view.state == "failed"
        assert callbacks == ["failed"]
    finally:
        release.set()
        coordinator.close()


def test_new_fingerprints_cannot_spawn_unbounded_blocked_workers() -> None:
    app = _RecordingApp()
    started: Queue[None] = Queue()
    release = Event()
    fingerprint = ["initial"]
    calls: list[int] = []

    def blocking_probe() -> FirstRunRuntimeSnapshot:
        calls.append(1)
        started.put(None)
        assert release.wait(3), "probe release was never signaled"
        return _snapshot()

    coordinator = FirstRunReadinessCoordinator(
        _context(),
        probe=blocking_probe,
        fingerprint=lambda: fingerprint[0],
        timeout_seconds=5,
        max_workers=2,
    )
    try:
        assert coordinator.request(app)
        started.get(timeout=3)
        fingerprint[0] = "changed"
        assert coordinator.request(app)
        started.get(timeout=3)
        fingerprint[0] = "newest"
        assert not coordinator.request(app)
        rejected_generation = coordinator.view.generation
        for _ in range(100):
            assert not coordinator.request(app)
        assert coordinator.view.generation == rejected_generation
        assert calls == [1, 1]
        assert coordinator.active_worker_count == 2
        assert coordinator.queued_worker_count == 0
        assert coordinator.timeout_timer_count <= 2
        assert coordinator.view.state == "failed"
        assert "Retry" in (coordinator.view.message or "")
        coordinator.close()
        assert coordinator.timeout_timer_count == 0
        assert not coordinator.request(app)
    finally:
        release.set()
        coordinator.close()


def test_app_close_suppresses_inflight_result_and_callback() -> None:
    app = _RecordingApp()
    started = Event()
    release = Event()
    callbacks: list[str] = []

    def blocked_probe() -> FirstRunRuntimeSnapshot:
        started.set()
        assert release.wait(3), "probe release was never signaled"
        return _snapshot()

    coordinator = FirstRunReadinessCoordinator(
        _context(), probe=blocked_probe, fingerprint=lambda: "closing", timeout_seconds=5
    )
    try:
        assert coordinator.request(app, lambda: callbacks.append("unexpected"))
        assert started.wait(3)
        coordinator.close()
        assert coordinator.timeout_timer_count == 0
        release.set()
        app.deliver()
        assert callbacks == []
        assert coordinator.view.state == "failed"
    finally:
        release.set()
        coordinator.close()


def test_superseded_probe_timers_are_cancelled_without_unbounded_growth() -> None:
    app = _RecordingApp()
    started: Queue[None] = Queue()
    release = Event()
    fingerprint = ["first"]

    def blocked_probe() -> FirstRunRuntimeSnapshot:
        started.put(None)
        assert release.wait(3), "probe release was never signaled"
        return _snapshot()

    coordinator = FirstRunReadinessCoordinator(
        _context(),
        probe=blocked_probe,
        fingerprint=lambda: fingerprint[0],
        timeout_seconds=5,
        max_workers=2,
    )
    try:
        assert coordinator.request(app)
        started.get(timeout=3)
        assert coordinator.timeout_timer_count == 1
        fingerprint[0] = "second"
        assert coordinator.request(app)
        started.get(timeout=3)
        assert coordinator.timeout_timer_count == 1
        fingerprint[0] = "third"
        assert not coordinator.request(app)
        assert coordinator.view.state == "failed"
        assert coordinator.active_worker_count == 2
        assert coordinator.timeout_timer_count == 0
    finally:
        release.set()
        coordinator.close()
