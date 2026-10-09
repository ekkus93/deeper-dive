"""Deterministic non-blocking first-run readiness regressions."""

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
from deeper_dive.guided_readiness import (
    FirstRunDerivedReadiness,
    _llm_runtime_ready,
    _tts_runtime_ready,
)
from deeper_dive.provider_tui import ProviderController
from deeper_dive.guided_workflow import WizardContext


class _ImmediateApp:
    def call_from_thread(self, callback, *args):
        return callback(*args)


def _snapshot(*, setup_ready: bool) -> FirstRunRuntimeSnapshot:
    readiness = FirstRunDerivedReadiness(
        llm_provider_ready=setup_ready,
        model_roles_ready=setup_ready,
        speech_choice_made=True,
        speech_deferred=True,
        audio_ready=False,
        ffmpeg_available=True,
        kitten_available=True,
        defaults_ready=setup_ready,
    )
    check = FirstRunSystemCheck(
        python_runtime="Python test",
        ffmpeg_available=True,
        kitten_available=True,
        ollama_reachable=False,
        llama_server_reachable=False,
        diagnostics=(),
    )
    return FirstRunRuntimeSnapshot(readiness, check)


def _context(step: str = "provider-config") -> WizardContext:
    state = SimpleNamespace(current_step=step)
    return cast(WizardContext, SimpleNamespace(state=state, composition=SimpleNamespace()))


def _wait(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true")


def test_duplicate_refreshes_coalesce_while_slow_probe_is_pending() -> None:
    started = Event()
    release = Event()
    calls = 0

    def probe() -> FirstRunRuntimeSnapshot:
        nonlocal calls
        calls += 1
        started.set()
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
    assert started.wait(1)
    assert not coordinator.request(app)
    assert coordinator.view.state == "checking"
    release.set()
    _wait(lambda: coordinator.view.state == "ready")
    assert calls == 1


def test_newer_configuration_wins_over_stale_slow_result() -> None:
    first_started = Event()
    first_release = Event()
    call_count = 0
    fingerprint = ["first"]

    def probe() -> FirstRunRuntimeSnapshot:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            first_started.set()
            assert first_release.wait(1)
            return _snapshot(setup_ready=False)
        return _snapshot(setup_ready=True)

    coordinator = FirstRunReadinessCoordinator(
        _context(),
        probe=probe,
        fingerprint=lambda: fingerprint[0],
        timeout_seconds=1,
    )
    app = _ImmediateApp()
    assert coordinator.request(app)
    assert first_started.wait(1)
    fingerprint[0] = "second"
    assert coordinator.request(app)
    _wait(lambda: coordinator.view.state == "ready")
    assert coordinator.snapshot is not None
    assert coordinator.snapshot.readiness.setup_ready
    first_release.set()
    time.sleep(0.03)
    assert coordinator.snapshot is not None
    assert coordinator.snapshot.readiness.setup_ready
    assert coordinator.view.generation == 2


def test_timeout_is_bounded_and_does_not_wait_for_slow_probe() -> None:
    release = Event()

    def probe() -> FirstRunRuntimeSnapshot:
        assert release.wait(1)
        return _snapshot(setup_ready=True)

    coordinator = FirstRunReadinessCoordinator(
        _context(),
        probe=probe,
        fingerprint=lambda: "slow",
        timeout_seconds=0.02,
    )
    assert coordinator.request(_ImmediateApp())
    _wait(lambda: coordinator.view.state == "failed")
    assert "timed out" in (coordinator.view.message or "")
    release.set()


def test_openai_readiness_reuses_one_model_discovery_call() -> None:
    runtime = SimpleNamespace(
        health_calls=0,
        model_calls=0,
    )

    def health():
        runtime.health_calls += 1
        return SimpleNamespace(healthy=True)

    def models():
        runtime.model_calls += 1
        return (SimpleNamespace(model="model-b"),)

    runtime.health = health
    runtime.models = models
    controller = cast(ProviderController, SimpleNamespace(llm=lambda name: runtime))
    assert _llm_runtime_ready(controller, "remote", "openai") == frozenset({"model-b"})
    assert runtime.health_calls == 0
    assert runtime.model_calls == 1


def test_non_openai_readiness_keeps_one_health_and_one_discovery_call() -> None:
    runtime = SimpleNamespace(health_calls=0, model_calls=0)

    def health():
        runtime.health_calls += 1
        return SimpleNamespace(healthy=True)

    def models():
        runtime.model_calls += 1
        return (SimpleNamespace(model="model-a"),)

    runtime.health = health
    runtime.models = models
    controller = cast(ProviderController, SimpleNamespace(llm=lambda name: runtime))
    assert _llm_runtime_ready(controller, "local", "ollama") == frozenset({"model-a"})
    assert runtime.health_calls == 1
    assert runtime.model_calls == 1


def test_elevenlabs_readiness_reuses_one_voice_discovery_call() -> None:
    runtime = SimpleNamespace(health_calls=0, voice_calls=0)

    def health():
        runtime.health_calls += 1
        return SimpleNamespace(healthy=True)

    def voices():
        runtime.voice_calls += 1
        return (SimpleNamespace(id="voice-a"),)

    runtime.health = health
    runtime.voices = voices
    controller = cast(ProviderController, SimpleNamespace(tts=lambda name: runtime))
    assert _tts_runtime_ready(controller, "speech", "voice-a", "elevenlabs")
    assert runtime.health_calls == 0
    assert runtime.voice_calls == 1
