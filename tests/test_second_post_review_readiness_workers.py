from __future__ import annotations

import time
from threading import Event
from types import SimpleNamespace
from typing import cast

from deeper_dive.first_run import FirstRunSystemCheck
from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunRuntimeSnapshot,
)
from deeper_dive.guided_readiness import FirstRunDerivedReadiness
from deeper_dive.guided_workflow import WizardContext


class _ImmediateApp:
    def post_message(self, message):
        message.run()
        return True


def _snapshot(*, setup_ready: bool) -> FirstRunRuntimeSnapshot:
    return FirstRunRuntimeSnapshot(
        FirstRunDerivedReadiness(
            llm_provider_ready=setup_ready,
            model_roles_ready=setup_ready,
            speech_choice_made=True,
            speech_deferred=True,
            audio_ready=False,
            ffmpeg_available=True,
            kitten_available=True,
            defaults_ready=setup_ready,
        ),
        FirstRunSystemCheck(
            python_runtime="Python test",
            ffmpeg_available=True,
            kitten_available=True,
            ollama_reachable=False,
            llama_server_reachable=False,
            diagnostics=(),
        ),
    )


def _context() -> WizardContext:
    state = SimpleNamespace(current_step="provider-config")
    return cast(WizardContext, SimpleNamespace(state=state, composition=SimpleNamespace()))


def _wait(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true")


def test_repeated_timeouts_never_exceed_readiness_worker_budget() -> None:
    release = Event()
    fingerprint = ["0"]

    def probe():
        assert release.wait(2)
        return _snapshot(setup_ready=True)

    coordinator = FirstRunReadinessCoordinator(
        _context(),
        probe=probe,
        fingerprint=lambda: fingerprint[0],
        timeout_seconds=0.01,
        max_workers=2,
    )
    app = _ImmediateApp()
    try:
        for index in range(8):
            fingerprint[0] = str(index)
            coordinator.request(app)
            time.sleep(0.02)
            assert coordinator.active_worker_count <= 2
        assert coordinator.active_worker_count == 2
        assert coordinator.view.state == "failed"
        assert "workers are still finishing" in (coordinator.view.message or "")
    finally:
        release.set()
    _wait(lambda: coordinator.active_worker_count == 0)


def test_close_stops_new_readiness_requests_and_late_publication() -> None:
    release = Event()

    def probe():
        assert release.wait(1)
        return _snapshot(setup_ready=True)

    coordinator = FirstRunReadinessCoordinator(
        _context(),
        probe=probe,
        fingerprint=lambda: "same",
        timeout_seconds=1,
    )
    app = _ImmediateApp()
    assert coordinator.request(app)
    _wait(lambda: coordinator.active_worker_count == 1)
    coordinator.close()
    assert coordinator.view.state == "failed"
    assert not coordinator.request(app)

    release.set()
    _wait(lambda: coordinator.active_worker_count == 0)
    time.sleep(0.02)
    assert coordinator.view.state == "failed"
    assert coordinator.snapshot is None
