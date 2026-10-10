from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_configuration import EpisodeConfigurationRepository
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.storage.workspace import WorkspaceManager


def _fixture(tmp_path: Path):
    clock = FrozenClock(datetime(2026, 10, 9, 12, 0, tzinfo=UTC))
    app_service = DeeperDiveService(WorkspaceManager(tmp_path / "data"), clock=clock)
    project = app_service.create_project("Lifecycle")
    database = Database(app_service.workspaces.project_root(project.id) / "project.db")
    repository = HostEpisodeRepository(database)
    repository.create_host(HostProfile("host-1", project.id, "Host One").to_record())
    service = EpisodeConfigurationService(database, clock=clock)
    episode = service.create(
        project.id,
        EpisodeConfiguration(
            title="Episode",
            focus="Focus",
            target_duration_seconds=120,
            host_ids=("host-1",),
        ),
    )
    timestamp = format_timestamp(clock.now())
    repository.save_plan(
        EpisodePlanRecord(
            id="plan-1",
            episode_id=episode.id,
            created_at=timestamp,
            modified_at=timestamp,
            plan_json='{"target_duration_seconds": 120}',
        ),
        [
            SegmentPlanRecord(
                id="segment-1",
                episode_plan_id="plan-1",
                ordinal=0,
                title="Opening",
                target_duration_seconds=120,
                segment_json='{"title":"Opening","target_duration_seconds":120}',
            )
        ],
    )
    return clock, database, repository, service, episode


def test_noop_episode_edit_preserves_plan_identity_and_modified_time(tmp_path: Path) -> None:
    _clock, _database, repository, service, episode = _fixture(tmp_path)
    before = repository.get_plan(episode.id)
    assert before is not None

    result = service.edit(episode.id, service.load_configuration(episode.id))

    after = repository.get_plan(episode.id)
    assert result == episode
    assert after is not None
    assert after.id == before.id
    assert after.modified_at == before.modified_at


def test_changed_draft_configuration_invalidates_plan_once(tmp_path: Path) -> None:
    _clock, _database, repository, service, episode = _fixture(tmp_path)
    current = service.load_configuration(episode.id)

    result = service.edit(episode.id, replace(current, focus="Changed focus"))

    assert result.state == "draft"
    assert service.load_configuration(episode.id).focus == "Changed focus"
    assert repository.get_plan(episode.id) is None


def test_configuration_edit_is_frozen_after_generation_run_exists(tmp_path: Path) -> None:
    clock, database, repository, service, episode = _fixture(tmp_path)
    current = service.load_configuration(episode.id)
    timestamp = format_timestamp(clock.now())
    GenerationRunRepository(database).create(
        GenerationRunRecord(
            id="run-1",
            episode_id=episode.id,
            stage="research",
            state="running",
            created_at=timestamp,
            modified_at=timestamp,
        )
    )

    with pytest.raises(ValueError, match="frozen after generation starts"):
        service.edit(episode.id, replace(current, focus="Unsafe late edit"))

    assert service.load_configuration(episode.id) == current
    assert repository.get_plan(episode.id) is not None


def test_non_draft_episode_is_never_demoted_by_configuration_edit(tmp_path: Path) -> None:
    _clock, database, repository, service, episode = _fixture(tmp_path)
    with database.transaction() as db:
        db.execute("UPDATE episodes SET state='completed' WHERE id=?", (episode.id,))
    completed = repository.get_episode(episode.id)
    assert completed is not None and completed.state == "completed"
    current = service.load_configuration(episode.id)

    # A semantic no-op is safe and does not rewrite historical state.
    result = service.edit(episode.id, current)
    assert result.state == "completed"
    assert repository.get_plan(episode.id) is not None

    with pytest.raises(ValueError, match="frozen after generation starts"):
        service.edit(episode.id, replace(current, title="Rewritten historical episode"))

    persisted = repository.get_episode(episode.id)
    assert persisted is not None and persisted.state == "completed"
    assert persisted.title == "Episode"
    assert repository.get_plan(episode.id) is not None


@pytest.mark.parametrize("run_state", ["running", "paused", "failed", "completed"])
def test_configuration_change_is_frozen_after_run_even_without_existing_plan(
    tmp_path: Path, run_state: str
) -> None:
    clock, database, repository, service, episode = _fixture(tmp_path)
    current = service.load_configuration(episode.id)
    with database.transaction() as db:
        db.execute(
            "DELETE FROM segment_plans WHERE episode_plan_id IN "
            "(SELECT id FROM episode_plans WHERE episode_id=?)",
            (episode.id,),
        )
        db.execute("DELETE FROM episode_plans WHERE episode_id=?", (episode.id,))
    assert repository.get_plan(episode.id) is None

    timestamp = format_timestamp(clock.now())
    GenerationRunRepository(database).create(
        GenerationRunRecord(
            id=f"run-{run_state}",
            episode_id=episode.id,
            stage="research",
            state=run_state,
            created_at=timestamp,
            modified_at=timestamp,
        )
    )

    with pytest.raises(ValueError, match="configuration is frozen"):
        service.edit(episode.id, replace(current, focus="Late configuration drift"))

    assert service.load_configuration(episode.id) == current



def test_stale_episode_configuration_writer_rejected_with_frozen_clock(tmp_path: Path) -> None:
    _clock, _database, repository, service, episode = _fixture(tmp_path)
    stale_record = repository.get_episode(episode.id)
    assert stale_record is not None
    current = service.load_configuration(episode.id)

    service.edit(episode.id, replace(current, focus="New durable focus"))
    durable = repository.get_episode(episode.id)
    assert durable is not None
    # Frozen clocks intentionally make timestamps equal; content CAS still detects drift.
    assert durable.modified_at == stale_record.modified_at

    stale_candidate = replace(
        stale_record,
        focus="Stale writer focus",
        config_json=service._record(
            stale_record.id,
            stale_record.project_id,
            stale_record.created_at,
            stale_record.modified_at,
            replace(current, focus="Stale writer focus"),
        ).config_json,
    )
    with pytest.raises(ValueError, match="changed concurrently"):
        EpisodeConfigurationRepository(_database).update(
            stale_candidate,
            list(current.host_ids),
            expected_config_json=stale_record.config_json,
        )

    persisted = repository.get_episode(episode.id)
    assert persisted is not None
    assert persisted.focus == "New durable focus"
