from __future__ import annotations

from pathlib import Path

from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.storage.database import Database


def _configuration(completed) -> tuple[str, tuple[str, ...]]:
    database = Database(
        completed.service.workspaces.project_root(completed.project_id) / "project.db"
    )
    config = EpisodeConfigurationService(database).load_configuration(completed.episode_id)
    return config.title, config.host_ids


def test_two_project_completed_acceptance_fixture_is_fully_isolated(
    two_project_completed_acceptance,
) -> None:
    matrix = two_project_completed_acceptance()
    first, second = matrix.first, matrix.second

    assert first.project_id != second.project_id
    assert first.episode_id != second.episode_id
    assert first.run_id != second.run_id
    assert set(first.turn_ids).isdisjoint(second.turn_ids)
    assert first.transcript_path != second.transcript_path
    assert first.audio_path != second.audio_path
    assert first.transcript_path.is_file() and second.transcript_path.is_file()
    assert first.audio_path.is_file() and second.audio_path.is_file()

    first_title, first_hosts = _configuration(first)
    second_title, second_hosts = _configuration(second)
    assert first_title == second_title == "Quick Deep Dive"
    assert first_hosts and second_hosts
    assert set(first_hosts).isdisjoint(second_hosts)

    for completed in (first, second):
        project_root = completed.service.workspaces.project_root(completed.project_id)
        assert completed.transcript_path.is_relative_to(project_root / "output")
        assert completed.audio_path.is_relative_to(project_root / "output")
        assert Path(completed.transcript_path).name.startswith(completed.episode_id)


def test_second_post_review_acceptance_fixture_includes_pending_run_and_snapshots(
    second_post_review_acceptance,
) -> None:
    matrix = second_post_review_acceptance()
    pending = matrix.completed.first.service.runs(matrix.pending_project_id).get(
        matrix.pending_run_id
    )
    assert pending is not None
    assert pending.episode_id == matrix.pending_episode_id
    assert pending.state == "pending"
    assert matrix.config_bytes.startswith(b"{")
    assert b'"quick_deep_dive_duration_minutes"' in matrix.config_bytes
    assert matrix.pending_config_snapshot.startswith(b"{")
    assert b'"host_ids"' in matrix.pending_config_snapshot
    assert len(set(matrix.identity_snapshot)) == len(matrix.identity_snapshot)
