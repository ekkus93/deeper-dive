from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.generation_start import select_or_create_generation_run
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("state", ["pending", "running", "paused"])
def test_generation_start_reuses_active_run(tmp_path: Path, state: str) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    active = _run(service, episode_id, state=state)
    service.runs(project_id).create(active)

    first = select_or_create_generation_run(service, project_id, episode_id)
    second = select_or_create_generation_run(service, project_id, episode_id)

    assert first.created is False
    assert first.run.id == active.id
    assert second.created is False
    assert second.run.id == active.id
    assert service.runs(project_id).latest_for_episode(episode_id) == active


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled"])
def test_generation_start_creates_new_run_after_terminal_run(tmp_path: Path, state: str) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    terminal = _run(service, episode_id, state=state)
    service.runs(project_id).create(terminal)

    result = select_or_create_generation_run(service, project_id, episode_id)

    assert result.created is True
    assert result.run.id != terminal.id
    assert result.run.state == "pending"
    assert result.run.stage == "sources"


def test_generation_start_replaces_active_run_with_cancel_requested(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    cancelling = replace(_run(service, episode_id, state="running"), cancel_requested=True)
    service.runs(project_id).create(cancelling)

    result = select_or_create_generation_run(service, project_id, episode_id)

    assert result.created is True
    assert result.run.id != cancelling.id
    assert result.run.state == "pending"


def test_generation_start_rejects_unknown_persisted_state(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    service.runs(project_id).create(_run(service, episode_id, state="mystery"))

    with pytest.raises(ValueError, match="unsupported run state"):
        select_or_create_generation_run(service, project_id, episode_id)


def _run(
    service: DeeperDiveService,
    episode_id: str,
    *,
    state: str,
) -> GenerationRunRecord:
    timestamp = format_timestamp(service.clock.now())
    return GenerationRunRecord(
        id=str(new_run_id()),
        episode_id=episode_id,
        stage="export" if state == "completed" else "sources",
        state=state,
        created_at=timestamp,
        modified_at=timestamp,
    )


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
