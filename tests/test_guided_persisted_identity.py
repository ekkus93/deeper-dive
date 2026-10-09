"""Restarted production host/plan/provider identity and multi-episode isolation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.model_roles import ModelRole
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tui import DeeperDiveApp


def test_restarted_guided_runtime_preserves_host_plan_and_provider_identity(
    completed_episode_acceptance: Callable[..., Any],
) -> None:
    """Two production episodes survive a fresh service without identity drift."""
    first = completed_episode_acceptance()
    second = completed_episode_acceptance(first.project_id)
    assert first.episode_id != second.episode_id
    assert first.run_id != second.run_id
    assert first.transcript_path != second.transcript_path
    assert first.audio_path != second.audio_path
    assert set(first.turn_ids).isdisjoint(second.turn_ids)

    restored = DeeperDiveService(WorkspaceManager(first.service.workspaces.data_dir))
    composition = ProductionComposition.build(service=restored)
    project_id = first.project_id
    hosts = restored.hosts(project_id).list_hosts(project_id)
    assert {host.display_name for host in hosts} == {
        "Fixture Host 1",
        "Fixture Host 2",
    }
    host_ids = {host.id for host in hosts}
    assert len(host_ids) == 2
    provider_config = composition.provider_controller.config()
    assert provider_config.providers["fake"].default_model == "fake-v1"
    assert provider_config.providers["speech"].provider_type == "fake-tts"
    for role in ModelRole:
        assert provider_config.defaults[role.value] == "fake:fake-v1"

    database = composition.database_for_project(project_id)
    episode_configs = EpisodeConfigurationService(database)
    planner = composition.configured_planning_service(project_id, "fake", "fake-v1")
    app = DeeperDiveApp(restored)
    app.current_project_id = project_id

    for completed in (first, second):
        config = episode_configs.load_configuration(completed.episode_id)
        assert set(config.host_ids) == host_ids
        plan = planner.load_plan(completed.episode_id)
        assert plan.episode_id == completed.episode_id
        assert plan.target_duration_seconds > 0
        assert plan.segments
        assert all(set(segment.lead_host_ids).issubset(host_ids) for segment in plan.segments)

        run = restored.runs(project_id).get(completed.run_id)
        assert run is not None and run.state == "completed"
        assert run.episode_id == completed.episode_id
        app.current_episode_id = completed.episode_id
        app.current_run_id = completed.run_id
        assert {turn.id for turn in TranscriptReviewController().turns(app)} == set(
            completed.turn_ids
        )
        assert AudioTimelineRepository(database).get(completed.episode_id) is not None
        assert completed.transcript_path.is_file()
        assert completed.audio_path.is_file()
