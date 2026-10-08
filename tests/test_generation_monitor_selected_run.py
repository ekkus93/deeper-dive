"""Run selection must never cross an episode/run identity boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def test_monitor_uses_explicit_selected_run_and_rejects_cross_episode_run(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 10, 8, 12, 0, tzinfo=UTC)),
    )
    project = service.create_project("Run selection")
    now = format_timestamp(service.clock.now())
    episode_ids = [str(new_episode_id()), str(new_episode_id())]
    for episode_id in episode_ids:
        service.hosts(project.id).create_episode(
            EpisodeRecord(
                id=episode_id,
                project_id=project.id,
                title=f"Episode {episode_id}",
                created_at=now,
                modified_at=now,
            ),
            [],
        )
    first_run, second_run, foreign_run = (str(new_run_id()) for _ in range(3))
    runs = service.runs(project.id)
    runs.create(GenerationRunRecord(first_run, episode_ids[0], "research", "paused", now, now))
    runs.create(GenerationRunRecord(second_run, episode_ids[0], "tts", "failed", now, now))
    runs.create(GenerationRunRecord(foreign_run, episode_ids[1], "export", "completed", now, now))

    app = DeeperDiveApp(service)
    app.current_project_id = project.id
    app.current_episode_id = episode_ids[0]
    controller = app.generation_monitor_controller

    app.current_run_id = first_run
    snapshot = controller.snapshot(app)
    assert snapshot.run is not None
    assert snapshot.run.id == first_run
    assert snapshot.run.state == "paused"

    app.current_run_id = second_run
    snapshot = controller.snapshot(app)
    assert snapshot.run is not None
    assert snapshot.run.id == second_run
    assert snapshot.run.state == "failed"

    app.current_run_id = foreign_run
    assert controller.snapshot(app).run is None
    app.current_run_id = "nonexistent-run"
    assert controller.snapshot(app).run is None

    # Legacy callers without an explicit selection still get the episode's
    # latest run, never a run from another episode.
    app.current_run_id = None
    fallback = controller.snapshot(app)
    assert fallback.run is not None
    assert fallback.run.episode_id == episode_ids[0]
