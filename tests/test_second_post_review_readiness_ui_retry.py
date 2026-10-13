"""SPR-03: production Textual readiness state and explicit retry acceptance."""

from __future__ import annotations

import asyncio
from threading import Event

from textual.widgets import Button, Static

from deeper_dive import guided_app as guided_app_module
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.first_run import FirstRunSystemCheck
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunRuntimeSnapshot,
)
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_readiness import FirstRunDerivedReadiness
from deeper_dive.storage.workspace import WorkspaceManager


def _snapshot() -> FirstRunRuntimeSnapshot:
    return FirstRunRuntimeSnapshot(
        readiness=FirstRunDerivedReadiness(
            llm_provider_ready=True,
            model_roles_ready=True,
            speech_choice_made=True,
            speech_deferred=True,
            audio_ready=False,
            ffmpeg_available=True,
            kitten_available=False,
            defaults_ready=True,
        ),
        system_check=FirstRunSystemCheck(
            python_runtime="Python test",
            ffmpeg_available=True,
            kitten_available=False,
            ollama_reachable=False,
            llama_server_reachable=False,
            diagnostics=(),
        ),
    )


def test_first_run_readiness_check_failure_and_explicit_retry(tmp_path, monkeypatch) -> None:
    asyncio.run(_exercise(tmp_path, monkeypatch))


async def _exercise(tmp_path, monkeypatch) -> None:
    started = Event()
    release_failure = Event()
    retry_started = Event()
    release_success = Event()
    attempts: list[int] = []

    def fake_probe() -> FirstRunRuntimeSnapshot:
        attempts.append(1)
        if len(attempts) == 1:
            started.set()
            assert release_failure.wait(5)
            raise RuntimeError("readiness probe temporarily unavailable")
        retry_started.set()
        assert release_success.wait(5)
        return _snapshot()

    def factory(context):
        return FirstRunReadinessCoordinator(
            context,
            probe=fake_probe,
            fingerprint=lambda: "stable-config",
            timeout_seconds=6,
            max_workers=1,
        )

    monkeypatch.setattr(guided_app_module, "FirstRunReadinessCoordinator", factory)
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    try:
        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            assert isinstance(screen, GuidedFirstRunWizard)
            screen.action_continue()
            assert screen.context.state.current_step == "system-check"
            button = screen.query_one("#setup-retry-readiness", Button)
            assert button.display

            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set()
            await pilot.pause()
            content = str(screen.query_one("#wizard-step-content", Static).render())
            assert "Checking provider and local runtime readiness" in content
            assert app._first_run_readiness.active_worker_count == 1

            release_failure.set()
            for _ in range(200):
                await pilot.pause()
                if app._first_run_readiness.view.state == "failed":
                    break
                await asyncio.sleep(0.01)
            assert app._first_run_readiness.view.state == "failed"
            content = str(screen.query_one("#wizard-step-content", Static).render())
            assert "needs attention" in content
            assert "retry" in content.casefold()

            button.press()
            for _ in range(200):
                await pilot.pause()
                if retry_started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert retry_started.is_set()
            content = str(screen.query_one("#wizard-step-content", Static).render())
            assert "Checking provider and local runtime readiness" in content
            for _ in range(10):
                button.press()
            await pilot.pause()
            assert attempts == [1, 1]
            assert app._first_run_readiness.active_worker_count == 1

            release_success.set()
            for _ in range(200):
                await pilot.pause()
                if app._first_run_readiness.view.state == "ready":
                    break
                await asyncio.sleep(0.01)
            assert app._first_run_readiness.view.state == "ready"
            content = str(screen.query_one("#wizard-step-content", Static).render())
            assert "Python/runtime: Ready" in content
            assert "FFmpeg: Ready" in content

            # Verify summary rendering independently of navigation prerequisites.
            screen.context.state = screen.context.state.moved_to("ready")
            screen._sync_text()
            screen._sync_setup_controls()
            summary = str(screen.query_one("#wizard-step-content", Static).render())
            assert "Language model: Ready" in summary
            assert "Model roles: Ready" in summary
            assert "Speech: intentionally deferred" in summary
            assert "Defaults: Ready" in summary
            assert screen.query_one("#setup-retry-readiness", Button).display
    finally:
        release_failure.set()
        release_success.set()
