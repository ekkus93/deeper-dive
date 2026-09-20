from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.generation_start import select_or_create_generation_run
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager


def test_generation_start_creates_one_pending_run_and_reuses_it(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)

    first = select_or_create_generation_run(service, project_id, episode_id)
    second = select_or_create_generation_run(service, project_id, episode_id)

    assert first.created is True
    assert first.run.state == "pending"
    assert first.run.stage == "sources"
    assert second.created is False
    assert second.run.id == first.run.id
    assert service.runs(project_id).latest_for_episode(episode_id) == first.run


def test_generation_start_creates_new_run_after_terminal_run(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    timestamp = format_timestamp(service.clock.now())
    completed = GenerationRunRecord(
        id=str(new_run_id()),
        episode_id=episode_id,
        stage="export",
        state="completed",
        created_at=timestamp,
        modified_at=timestamp,
    )
    service.runs(project_id).create(completed)

    result = select_or_create_generation_run(service, project_id, episode_id)

    assert result.created is True
    assert result.run.id != completed.id
    assert result.run.state == "pending"


def _episode(tmp_path: Path) -> tuple[DeeperDiveService, str, str]:
    clock = FrozenClock(datetime(2026, 9, 20, 20, 0, tzinfo=UTC))
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"), clock=clock)
    project = service.create_project("Generation start")
    episode_id = str(new_episode_id())
    timestamp = format_timestamp(clock.now())
    service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            created_at=timestamp,
            modified_at=timestamp,
        ),
        [],
    )
    return service, project.id, episode_id
