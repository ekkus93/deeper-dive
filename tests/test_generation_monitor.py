from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.generation_monitor import GenerationMonitorController, GenerationMonitorScreen
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import CompletedUnitRecord, GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewScreen
from deeper_dive.tui import DeeperDiveApp


def test_monitor_renders_durable_progress_and_controls(tmp_path: Path) -> None:
    asyncio.run(_monitor_renders_durable_progress_and_controls(tmp_path))


async def _monitor_renders_durable_progress_and_controls(tmp_path: Path) -> None:
    service, project_id, episode_id, run_id = _fixture(tmp_path)
    repository = service.runs(project_id)
    now = format_timestamp(service.clock.now())
    repository.complete_unit(CompletedUnitRecord(run_id, "sources", "stage", now))
    repository.complete_unit(CompletedUnitRecord(run_id, "research", "gap-1", now))
    repository.complete_unit(CompletedUnitRecord(run_id, "tts", "turn-1", now))
    app = DeeperDiveApp(service, generation_monitor_controller=GenerationMonitorController())
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project_id
        app.current_episode_id = episode_id
        app.current_run_id = run_id
        app.action_navigate("monitor")
        await pilot.pause()
        screen = _monitor(app)
        assert "✓ sources" in _text(screen, "#stage-checklist")
        assert "○ research" in _text(screen, "#stage-checklist")
        assert "TTS progress: 1 completed unit(s)" in _text(screen, "#tts-progress")
        assert "Research progress: 1 completed unit(s)" in _text(screen, "#research-progress")
        screen.action_pause()
        assert service.runs(project_id).get(run_id).pause_requested is True  # type: ignore[union-attr]
        screen.action_resume()
        resumed = service.runs(project_id).get(run_id)
        assert resumed is not None and resumed.pause_requested is False
        screen.action_cancel()
        assert service.runs(project_id).get(run_id).cancel_requested is True  # type: ignore[union-attr]
        screen.action_diagnostics()
        assert "Run: " in _text(screen, "#diagnostics-summary")
        screen.action_view_transcript()
        await pilot.pause()
        assert isinstance(app.screen, TranscriptReviewScreen)


def test_monitor_rejects_resume_when_run_is_not_paused(tmp_path: Path) -> None:
    asyncio.run(_monitor_rejects_resume_when_run_is_not_paused(tmp_path))


async def _monitor_rejects_resume_when_run_is_not_paused(tmp_path: Path) -> None:
    service, project_id, episode_id, run_id = _fixture(tmp_path)
    repository = service.runs(project_id)
    run = repository.get(run_id)
    assert run is not None
    repository.update(replace(run, state="completed", pause_requested=False))
    app = DeeperDiveApp(service, generation_monitor_controller=GenerationMonitorController())
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project_id
        app.current_episode_id = episode_id
        app.current_run_id = run_id
        app.action_navigate("monitor")
        await pilot.pause()
        screen = _monitor(app)
        screen.action_resume()
        await pilot.pause()
        assert (
            "Only paused or pause-requested runs can resume"
            in _text(screen, "#screen-status")
        )
        assert repository.get(run_id).state == "completed"  # type: ignore[union-attr]


def test_long_running_fake_provider_does_not_block_tui(tmp_path: Path) -> None:
    asyncio.run(_long_running_fake_provider_does_not_block_tui(tmp_path))


async def _long_running_fake_provider_does_not_block_tui(tmp_path: Path) -> None:
    service, project_id, episode_id, run_id = _fixture(tmp_path)

    def slow_runner(selected_run_id: str, progress) -> None:
        assert selected_run_id == run_id
        progress(type("Event", (), {"operation": "conversation", "state": "running"})())
        time.sleep(0.25)

    controller = GenerationMonitorController(runner=slow_runner)
    app = DeeperDiveApp(service, generation_monitor_controller=controller)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project_id
        app.current_episode_id = episode_id
        app.current_run_id = run_id
        app.action_navigate("monitor")
        await pilot.pause()
        screen = _monitor(app)
        screen.start_background_generation()
        await asyncio.sleep(0.02)
        screen.action_diagnostics()
        await pilot.pause()
        assert "Run: " in _text(screen, "#diagnostics-summary")
        assert screen._task is not None and not screen._task.done()
        await screen._task


def test_background_generation_failure_uses_actionable_status(tmp_path: Path) -> None:
    asyncio.run(_background_generation_failure_uses_actionable_status(tmp_path))


async def _background_generation_failure_uses_actionable_status(tmp_path: Path) -> None:
    service, project_id, episode_id, run_id = _fixture(tmp_path)

    def failing_runner(selected_run_id: str, progress) -> None:
        assert selected_run_id == run_id
        raise RuntimeError("provider exploded with low-level detail")

    controller = GenerationMonitorController(runner=failing_runner)
    app = DeeperDiveApp(service, generation_monitor_controller=controller)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project_id
        app.current_episode_id = episode_id
        app.current_run_id = run_id
        app.action_navigate("monitor")
        await pilot.pause()
        screen = _monitor(app)
        screen.start_background_generation()
        assert screen._task is not None
        await screen._task
        await pilot.pause()
        status = _text(screen, "#screen-status")
        assert "Generation failed." in status
        assert "low-level detail" not in status


def _fixture(tmp_path: Path) -> tuple[DeeperDiveService, str, str, str]:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 19, 9, 0, tzinfo=UTC)),
    )
    project = service.create_project("Monitor")
    now = format_timestamp(service.clock.now())
    episode_id = str(new_episode_id())
    service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            created_at=now,
            modified_at=now,
        ),
        [],
    )
    run_id = str(new_run_id())
    service.runs(project.id).create(
        GenerationRunRecord(run_id, episode_id, "research", "running", now, now)
    )
    return service, project.id, episode_id, run_id


def _monitor(app: DeeperDiveApp) -> GenerationMonitorScreen:
    assert isinstance(app.screen, GenerationMonitorScreen)
    return app.screen


def _text(screen: GenerationMonitorScreen, selector: str) -> str:
    return str(screen.query_one(selector, Static).render())
