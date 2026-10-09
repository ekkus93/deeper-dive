from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.conversation_state import ConversationStateRepository
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.generation_monitor import GenerationMonitorController, GenerationMonitorScreen
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import CompletedUnitRecord, GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewScreen
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_errors import user_status


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
        paused_run = service.runs(project_id).get(run_id)
        assert paused_run is not None and paused_run.pause_requested is True
        paused = app.composition.generation_pipeline(project_id).run(run_id)
        assert paused.run.state == "paused"
        screen.action_resume()
        resumed = service.runs(project_id).get(run_id)
        assert resumed is not None and resumed.state == "pending"
        assert resumed.pause_requested is False
        screen.action_cancel()
        cancelled = service.runs(project_id).get(run_id)
        assert cancelled is not None and cancelled.cancel_requested is True
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
        assert "Only paused runs or retryable failed stages can resume" in _text(
            screen, "#screen-status"
        )
        completed = repository.get(run_id)
        assert completed is not None and completed.state == "completed"


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


def test_failed_background_runner_maps_to_actionable_sanitized_status(
    tmp_path: Path,
) -> None:
    """Bound the runner without an unbounded Textual Pilot drain."""
    _service, _project_id, _episode_id, run_id = _fixture(tmp_path)

    def failing_runner(selected_run_id: str, progress) -> None:
        assert selected_run_id == run_id
        raise RuntimeError("provider exploded with low-level detail")

    controller = GenerationMonitorController(runner=failing_runner)
    with pytest.raises(RuntimeError, match="provider exploded") as error:
        asyncio.run(controller.run(run_id))
    status = user_status("generation", error.value)
    assert "Generation failed." in status
    assert "Open diagnostics" in status
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


def test_monitor_diagnostics_and_status_redact_persisted_credential_canaries(
    tmp_path: Path,
) -> None:
    asyncio.run(_monitor_diagnostics_redact_persisted_credential_canaries(tmp_path))


async def _monitor_diagnostics_redact_persisted_credential_canaries(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id, run_id = _fixture(tmp_path)
    repository = service.runs(project_id)
    run = repository.get(run_id)
    assert run is not None
    secret = "synthetic-canary-credential"
    repository.update(
        replace(
            run,
            state="failed",
            failure_code="provider_auth_failed",
            failure_message=f"Authorization: Bearer {secret}",
        )
    )
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project_id
        app.current_episode_id = episode_id
        app.current_run_id = run_id
        app.action_navigate("monitor")
        await pilot.pause()
        monitor = _monitor(app)
        monitor.action_diagnostics()
        diagnostics = _text(monitor, "#diagnostics-summary")
        assert "provider_auth_failed" in diagnostics
        assert secret not in diagnostics
        assert "[REDACTED]" in diagnostics
        monitor._status(f"Authorization: Bearer {secret}")
        status = _text(monitor, "#screen-status")
        assert secret not in status
        assert "[REDACTED]" in status
