"""Second post-review regression coverage for episode edit/plan lifecycle."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest

from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_configuration import EpisodeConfigurationRepository
from deeper_dive.storage.episode_plan_repository import EpisodePlanRepository
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord


def _episode_with_plan(tmp_path, config: EpisodeConfiguration | None = None):
    database = Database(tmp_path / "project.db")
    CorpusRepository(database).create_project(ProjectRecord("project", "Project", "now", "now"))
    service = EpisodeConfigurationService(database)
    config = config or EpisodeConfiguration(title="Original", focus="initial focus")
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


def test_stale_planner_write_cannot_restore_plan_after_episode_edit(tmp_path) -> None:
    database, service, repository, episode, config = _episode_with_plan(tmp_path)
    current = repository.get_episode(episode.id)
    assert current is not None
    old_config_json = current.config_json

    service.edit(episode.id, replace(config, focus="new research focus"))
    assert repository.get_plan(episode.id) is None

    with pytest.raises(ValueError, match="configuration changed while the plan was being built"):
        EpisodePlanRepository(database).replace(
            EpisodePlanRecord(
                id="stale-plan",
                episode_id=episode.id,
                created_at="now",
                modified_at="now",
            ),
            [],
            expected_episode_config_json=old_config_json,
        )
    assert repository.get_plan(episode.id) is None


def test_state_change_during_edit_prevents_plan_loss(tmp_path) -> None:
    database, _service, repository, episode, _config = _episode_with_plan(tmp_path)
    original = repository.get_episode(episode.id)
    assert original is not None
    with database.transaction(immediate=True) as db:
        db.execute("UPDATE episodes SET state='running' WHERE id=?", (episode.id,))

    proposal = replace(original, focus="stale proposal")
    with pytest.raises(ValueError, match="no longer editable"):
        EpisodeConfigurationRepository(database).update(
            proposal,
            [],
            expected_config_json=original.config_json,
        )

    actual = repository.get_episode(episode.id)
    assert actual is not None and actual.state == "running"
    assert actual.focus == original.focus
    plan = repository.get_plan(episode.id)
    assert plan is not None and plan.id == "plan-original"
    assert [item.id for item in repository.list_segments(plan.id)] == ["segment-original"]


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "Retitled episode"},
        {"focus": "different source question"},
        {"audience": "expert"},
        {"technical_depth": "deep"},
        {"target_duration_seconds": 900},
        {"style": "debate"},
        {"must_cover": ("critical detail",)},
        {"avoid_topics": ("irrelevant context",)},
        {"source_overrides": {"source-one": False}},
        {"research_overrides": {"mode": "off"}},
        {"model_overrides": {"episode_planning": {"provider": "fake", "model": "fake-v2"}}},
    ],
)
def test_episode_edit_plan_impact_matrix_invalidates_only_meaningful_draft_changes(
    tmp_path, changes
) -> None:
    # All fields participate in EpisodePlannerService's request snapshot,
    # so a title change cannot be treated as non-plan-affecting metadata.
    _database, service, repository, episode, config = _episode_with_plan(tmp_path)
    original_plan = repository.get_plan(episode.id)
    assert original_plan is not None

    edited = service.edit(episode.id, replace(config, **changes))

    assert edited.state == "draft"
    assert repository.get_plan(episode.id) is None
    assert (
        service.load_configuration(episode.id).snapshot() == replace(config, **changes).snapshot()
    )


def test_semantically_identical_mapping_order_is_a_true_noop(tmp_path) -> None:
    config = EpisodeConfiguration(
        title="Original",
        focus="initial focus",
        source_overrides={"source-a": True, "source-b": False},
        research_overrides={"alpha": 1, "beta": 2},
        model_overrides={
            "directing": {"provider": "fake", "model": "fake-v1"},
            "verification": {"provider": "fake", "model": "fake-v1"},
        },
    )
    _database, service, repository, episode, _config = _episode_with_plan(tmp_path, config)
    before = repository.get_episode(episode.id)
    before_plan = repository.get_plan(episode.id)
    assert before is not None and before_plan is not None

    equivalent = replace(
        config,
        source_overrides={"source-b": False, "source-a": True},
        research_overrides={"beta": 2, "alpha": 1},
        model_overrides={
            "verification": {"model": "fake-v1", "provider": "fake"},
            "directing": {"model": "fake-v1", "provider": "fake"},
        },
    )
    assert service.edit(episode.id, equivalent) == before
    assert repository.get_episode(episode.id) == before
    assert repository.get_plan(episode.id) == before_plan
    assert [item.id for item in repository.list_segments(before_plan.id)] == ["segment-original"]


def test_failed_plan_invalidation_rolls_back_episode_and_host_changes(tmp_path) -> None:
    database, service, repository, episode, config = _episode_with_plan(tmp_path)
    repository.create_host(HostProfile("new-host", "project", "New Host").to_record())
    before = repository.get_episode(episode.id)
    before_plan = repository.get_plan(episode.id)
    before_hosts = repository.list_episode_host_ids(episode.id)
    assert before is not None and before_plan is not None

    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_plan_deletion
            BEFORE DELETE ON segment_plans
            BEGIN SELECT RAISE(ABORT, 'injected plan delete failure'); END
            """
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected plan delete failure"):
        service.edit(
            episode.id,
            replace(config, title="Rejected update", host_ids=("new-host",)),
        )

    assert repository.get_episode(episode.id) == before
    assert repository.get_plan(episode.id) == before_plan
    assert repository.list_episode_host_ids(episode.id) == before_hosts
    assert [item.id for item in repository.list_segments(before_plan.id)] == ["segment-original"]


def test_stale_configuration_writer_cannot_delete_newer_plan(tmp_path) -> None:
    database, service, repository, episode, config = _episode_with_plan(tmp_path)
    stale = repository.get_episode(episode.id)
    assert stale is not None
    service.edit(episode.id, replace(config, focus="first edit"))
    repository.save_plan(
        EpisodePlanRecord(
            id="newer-plan",
            episode_id=episode.id,
            created_at="now",
            modified_at="now",
        ),
        [
            SegmentPlanRecord(
                id="newer-segment",
                episode_plan_id="newer-plan",
                ordinal=0,
                title="New plan",
                target_duration_seconds=1800,
                segment_json='{"title":"New plan","target_duration_seconds":1800}',
            )
        ],
    )
    pending = replace(
        stale,
        focus="stale second edit",
        config_json=json.dumps(
            replace(config, focus="stale second edit").snapshot(),
            sort_keys=True,
        ),
    )
    with pytest.raises(ValueError, match="changed concurrently"):
        EpisodeConfigurationRepository(database).update(
            pending, [], expected_config_json=stale.config_json
        )
    assert repository.get_plan(episode.id).id == "newer-plan"
    assert service.load_configuration(episode.id).focus == "first edit"
    assert [s.id for s in repository.list_segments("newer-plan")] == ["newer-segment"]


def test_reject_cross_project_host_before_deleting_existing_plan(tmp_path) -> None:
    database, service, repository, episode, config = _episode_with_plan(tmp_path)
    CorpusRepository(database).create_project(ProjectRecord("other-project", "Other", "now", "now"))
    repository.create_host(HostProfile("other-host", "other-project", "Other Host").to_record())
    before = repository.get_episode(episode.id)
    original_plan = repository.get_plan(episode.id)
    assert before is not None and original_plan is not None

    with pytest.raises(ValueError, match="does not belong to project"):
        service.edit(episode.id, replace(config, host_ids=("other-host",)))
    assert repository.get_episode(episode.id) == before
    assert repository.get_plan(episode.id) == original_plan
    assert repository.list_episode_host_ids(episode.id) == []
