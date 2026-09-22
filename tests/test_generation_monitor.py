from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.conversation_state import ConversationStateRepository
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.generation_monitor import GenerationMonitorController, GenerationMonitorScreen
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.storage.database import Database
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
        composition = service._production_composition  # type: ignore[attr-defined]
        paused = composition.generation_pipeline(project_id).run(run_id)
        assert paused.run.state == "paused"
        screen.action_resume()
        resumed = service.runs(project_id).get(run_id)
        assert resumed is not None and resumed.state == "pending"
        assert resumed.pause_requested is False
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
        assert "Only durably paused runs can resume" in _text(screen, "#screen-status")
        assert repository.get(run_id).state == "completed"  # type: ignore[union-attr]


def test_monitor_binds_conversation_state_and_recent_turns(tmp_path: Path) -> None:
    asyncio.run(_monitor_binds_conversation_state_and_recent_turns(tmp_path))


async def _monitor_binds_conversation_state_and_recent_turns(tmp_path: Path) -> None:
    service, project_id, episode_id, run_id = _fixture(tmp_path)
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    ConversationStateRepository(database).update(episode_id, segment_ordinal=2, segment_turn=3)
    with database.transaction() as connection:
        connection.execute(
            """CREATE TABLE conversation_turns(
                id TEXT PRIMARY KEY,
                episode_id TEXT NOT NULL,
                text TEXT NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO conversation_turns(id, episode_id, text) VALUES (?, ?, ?)",
            ("turn-1", episode_id, "First durable monitor turn."),
        )
        connection.execute(
            "INSERT INTO conversation_turns(id, episode_id, text) VALUES (?, ?, ?)",
            ("turn-2", episode_id, "Second durable monitor turn."),
        )
    app = DeeperDiveApp(service, generation_monitor_controller=GenerationMonitorController())
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project_id
        app.current_episode_id = episode_id
        app.current_run_id = run_id
        app.action_navigate("monitor")
        await pilot.pause()
        screen = _monitor(app)
        assert "Current section/turn: 2 / 3" in _text(screen, "#current-work")
        recent = _text(screen, "#recent-turns")
        assert "turn-1: First durable monitor turn." in recent
        assert "turn-2: Second durable monitor turn." in recent


def test_long_running_fake_provider_does_not_block_tui(tmp_path: Path) -> None:
    asyncio.run(_long_running_fake_provider_does_not_block_tui(tmp_path))


async def _long_running_fake_provider_does_not_block_tui(tmp_path: Path) -> None:
    _, _, _, run_id = _fixture(tmp_path)
    runner_started = threading.Event()
    release_runner = threading.Event()

    def slow_runner(selected_run_id: str, progress) -> None:
        assert selected_run_id == run_id
        progress(type("Event", (), {"operation": "conversation", "state": "running"})())
        runner_started.set()
        if not release_runner.wait(timeout=2.0):
            raise TimeoutError("test runner was not released")

    controller = GenerationMonitorController(runner=slow_runner)
    task = asyncio.create_task(controller.run(run_id))
    try:
        for _ in range(100):
            if runner_started.is_set():
                break
            await asyncio.sleep(0.01)
        assert runner_started.is_set()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release_runner.set()
    await asyncio.wait_for(task, timeout=5.0)


def test_production_monitor_runner_executes_pipeline_from_tui(tmp_path: Path) -> None:
    asyncio.run(_production_monitor_runner_executes_pipeline_from_tui(tmp_path))


async def _production_monitor_runner_executes_pipeline_from_tui(tmp_path: Path) -> None:
    service, project_id, episode_id, run_id = _fixture(tmp_path)
    repository = service.runs(project_id)
    run = repository.get(run_id)
    assert run is not None
    repository.update(replace(run, state="pending", stage=DEFAULT_STAGES[0]))
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project_id
        app.current_episode_id = episode_id
        app.current_run_id = run_id
        app.action_navigate("monitor")
        await pilot.pause()
        screen = _monitor(app)
        screen.start_background_generation()
        assert screen._task is not None
        await asyncio.wait_for(screen._task, timeout=5.0)
        await pilot.pause()
        completed = repository.get(run_id)
        assert completed is not None
        assert completed.state == "completed"
        assert repository.list_completed_stages(run_id) == list(DEFAULT_STAGES)
        assert "completed" in _text(screen, "#generation-state")


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
        await asyncio.wait_for(screen._task, timeout=5.0)
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
