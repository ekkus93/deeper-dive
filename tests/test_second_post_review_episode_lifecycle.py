"""Second post-review regression coverage for episode edit/plan lifecycle."""

from __future__ import annotations

from dataclasses import replace

import pytest

from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord


def _episode_with_plan(tmp_path):
    database = Database(tmp_path / "project.db")
    CorpusRepository(database).create_project(ProjectRecord("project", "Project", "now", "now"))
    service = EpisodeConfigurationService(database)
    config = EpisodeConfiguration(title="Original", focus="initial focus")
    episode = service.create("project", config)
    repository = HostEpisodeRepository(database)
    repository.save_plan(
        EpisodePlanRecord(
            id="plan-original",
            episode_id=episode.id,
            created_at="now",
            modified_at="now",
            plan_json='{"target_duration_seconds": 1800}',
        ),
        [
            SegmentPlanRecord(
                id="segment-original",
                episode_plan_id="plan-original",
                ordinal=0,
                title="Opening",
                target_duration_seconds=1800,
                segment_json='{"title": "Opening", "target_duration_seconds": 1800}',
            )
        ],
    )
    return database, service, repository, episode, config


def test_noop_episode_edit_preserves_plan_segment_and_episode_identity(tmp_path) -> None:
    _db, service, repository, episode, config = _episode_with_plan(tmp_path)
    before = repository.get_episode(episode.id)
    assert before is not None

    unchanged = service.edit(episode.id, config)

    assert unchanged == before
    assert repository.get_episode(episode.id) == before
    plan = repository.get_plan(episode.id)
    assert plan is not None
    assert plan.id == "plan-original"
    assert [segment.id for segment in repository.list_segments(plan.id)] == ["segment-original"]


def test_meaningful_draft_edit_invalidates_only_edited_episode_plan(tmp_path) -> None:
    _db, service, repository, episode, config = _episode_with_plan(tmp_path)
    other = service.create("project", EpisodeConfiguration(title="Other"))
    repository.save_plan(
        EpisodePlanRecord(
            id="other-plan",
            episode_id=other.id,
            created_at="now",
            modified_at="now",
        ),
        [],
    )

    edited = service.edit(episode.id, replace(config, focus="revised focus"))

    assert edited.state == "draft"
    assert service.load_configuration(episode.id).focus == "revised focus"
    assert repository.get_plan(episode.id) is None
    assert repository.get_plan(other.id) is not None
    assert repository.get_plan(other.id).id == "other-plan"


@pytest.mark.parametrize("state", ["planned", "running", "paused", "failed", "completed"])
def test_non_draft_episode_edit_cannot_demote_state_or_delete_plan(tmp_path, state) -> None:
    database, service, repository, episode, config = _episode_with_plan(tmp_path)
    with database.transaction() as db:
        db.execute("UPDATE episodes SET state=? WHERE id=?", (state, episode.id))

    original = repository.get_episode(episode.id)
    assert original is not None
    assert original.state == state

    with pytest.raises(ValueError, match="frozen after generation starts"):
        service.edit(episode.id, replace(config, focus="revised focus"))

    assert repository.get_episode(episode.id) == original
    plan = repository.get_plan(episode.id)
    assert plan is not None
    assert plan.id == "plan-original"
    assert [segment.id for segment in repository.list_segments(plan.id)] == ["segment-original"]
    assert service.edit(episode.id, config) == original
