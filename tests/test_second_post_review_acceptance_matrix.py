"""Reuse shared two-project acceptance fixtures to qualify episode/artifact identity."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.storage.episode_repositories import HostEpisodeRepository


def _digest(path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_shared_completed_and_pending_episodes_preserve_identity_on_edits(
    second_post_review_acceptance,
) -> None:
    fixture = second_post_review_acceptance()
    first = fixture.completed.first
    second = fixture.completed.second
    service = first.service
    assert service is second.service
    assert first.project_id != second.project_id
    assert first.episode_id != second.episode_id
    assert first.run_id != second.run_id
    assert first.audio_path != second.audio_path
    assert first.transcript_path != second.transcript_path
    assert set(first.turn_ids).isdisjoint(second.turn_ids)

    composition = ProductionComposition.build(service=service)
    completed = (first, second)
    for item in completed:
        database = composition.database_for_project(item.project_id)
        repository = HostEpisodeRepository(database)
        config_service = EpisodeConfigurationService(database)
        before_episode = repository.get_episode(item.episode_id)
        before_plan = repository.get_plan(item.episode_id)
        before_run = service.runs(item.project_id).get(item.run_id)
        assert before_episode is not None
        assert before_plan is not None
        assert before_run is not None and before_run.state == "completed"
        segment_ids = tuple(segment.id for segment in repository.list_segments(before_plan.id))
        original_audio = _digest(item.audio_path)
        original_transcript = _digest(item.transcript_path)
        existing_config = config_service.load_configuration(item.episode_id)

        assert config_service.edit(item.episode_id, existing_config) == before_episode

        assert repository.get_episode(item.episode_id) == before_episode
        assert repository.get_plan(item.episode_id) == before_plan
        assert (
            tuple(segment.id for segment in repository.list_segments(before_plan.id)) == segment_ids
        )
        assert service.runs(item.project_id).get(item.run_id) == before_run
        assert _digest(item.audio_path) == original_audio
        assert _digest(item.transcript_path) == original_transcript

    pending_db = composition.database_for_project(fixture.pending_project_id)
    pending_configuration = EpisodeConfigurationService(pending_db)
    pending_repository = HostEpisodeRepository(pending_db)
    original = pending_repository.get_episode(fixture.pending_episode_id)
    pending_plan = pending_repository.get_plan(fixture.pending_episode_id)
    pending_run = service.runs(fixture.pending_project_id).get(fixture.pending_run_id)
    assert original is not None
    assert pending_plan is not None
    assert pending_run is not None and pending_run.state == "pending"
    pending_config = pending_configuration.load_configuration(fixture.pending_episode_id)

    with pytest.raises(ValueError, match="frozen after generation starts"):
        pending_configuration.edit(
            fixture.pending_episode_id, replace(pending_config, focus="stale edit")
        )

    assert pending_repository.get_episode(fixture.pending_episode_id) == original
    assert pending_repository.get_plan(fixture.pending_episode_id) == pending_plan
    assert service.runs(fixture.pending_project_id).get(fixture.pending_run_id) == pending_run
    assert (service.workspaces.data_dir / "config.json").read_bytes() == fixture.config_bytes


def test_reopened_composition_rejects_historical_episode_edits(
    second_post_review_acceptance,
) -> None:
    """Restarted production services must preserve completed and pending artifacts."""
    fixture = second_post_review_acceptance()
    reopened = ProductionComposition.build(
        data_dir=fixture.completed.first.service.workspaces.data_dir
    )

    for item in (fixture.completed.first, fixture.completed.second):
        database = reopened.database_for_project(item.project_id)
        repository = HostEpisodeRepository(database)
        config_service = EpisodeConfigurationService(database)
        original_episode = repository.get_episode(item.episode_id)
        original_plan = repository.get_plan(item.episode_id)
        original_run = reopened.service.runs(item.project_id).get(item.run_id)
        assert original_episode is not None and original_plan is not None
        assert original_run is not None and original_run.state == "completed"
        segments = repository.list_segments(original_plan.id)
        original_config = config_service.load_configuration(item.episode_id)
        transcript_hash = _digest(item.transcript_path)
        audio_hash = _digest(item.audio_path)

        assert config_service.edit(item.episode_id, original_config) == original_episode
        with pytest.raises(ValueError, match="frozen after generation starts"):
            config_service.edit(
                item.episode_id, replace(original_config, focus="restarted stale edit")
            )

        assert repository.get_episode(item.episode_id) == original_episode
        assert repository.get_plan(item.episode_id) == original_plan
        assert repository.list_segments(original_plan.id) == segments
        assert reopened.service.runs(item.project_id).get(item.run_id) == original_run
        assert _digest(item.transcript_path) == transcript_hash
        assert _digest(item.audio_path) == audio_hash

    pending_db = reopened.database_for_project(fixture.pending_project_id)
    pending_repo = HostEpisodeRepository(pending_db)
    pending_service = EpisodeConfigurationService(pending_db)
    pending_episode = pending_repo.get_episode(fixture.pending_episode_id)
    pending_plan = pending_repo.get_plan(fixture.pending_episode_id)
    pending_run = reopened.service.runs(fixture.pending_project_id).get(fixture.pending_run_id)
    assert pending_episode is not None and pending_plan is not None
    assert pending_run is not None and pending_run.state == "pending"
    with pytest.raises(ValueError, match="frozen after generation starts"):
        pending_service.edit(
            fixture.pending_episode_id,
            replace(
                pending_service.load_configuration(fixture.pending_episode_id),
                focus="restarted pending edit",
            ),
        )
    assert pending_repo.get_episode(fixture.pending_episode_id) == pending_episode
    assert pending_repo.get_plan(fixture.pending_episode_id) == pending_plan
    assert reopened.service.runs(fixture.pending_project_id).get(
        fixture.pending_run_id
    ) == pending_run
    assert (
        reopened.service.workspaces.data_dir / "config.json"
    ).read_bytes() == fixture.config_bytes
