"""Reopen completed production episodes through persisted guided and advanced surfaces."""

from __future__ import annotations

import asyncio
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController


def test_preexisting_completed_project_survives_new_guided_app_restart(
    completed_episode_acceptance,
) -> None:
    created = completed_episode_acceptance(None)
    asyncio.run(_reopen_completed_guided_project(created))


async def _reopen_completed_guided_project(created) -> None:
    # Simulate a fresh process: do not reuse the composition/controller that
    # generated the episode or any in-memory runtime identity.
    service = DeeperDiveService(WorkspaceManager(created.service.workspaces.data_dir))
    project = service.open_project(created.project_id)
    assert project is not None
    assert service.list_sources(project.id)
    assert service.hosts(project.id).list_hosts(project.id)
    assert any(
        episode.id == created.episode_id
        for episode in service.hosts(project.id).list_episodes(project.id)
    )
    run = service.runs(project.id).get(created.run_id)
    assert run is not None and run.state == "completed"
    assert created.transcript_path.is_file() and created.audio_path.is_file()
    assert AudioTimelineRepository(
        service.workspaces.project_root(project.id) / "project.db"
    ) is not None

    app = GuidedDeeperDiveApp(service)
    app.current_project_id = project.id
    app.current_project_name = project.name
    app.current_episode_id = created.episode_id
    app.current_run_id = created.run_id
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.screen.id == "screen-home"
        assert "fake" in app.provider_controller.config().providers
        for destination in (
            "sources",
            "research",
            "hosts",
            "providers",
            "settings",
            "episode",
            "library",
        ):
            app.action_navigate(destination)
            await pilot.pause()
            assert app.screen is not None
            assert app.current_project_id == project.id
        assert [turn.id for turn in TranscriptReviewController().turns(app)] == list(
            created.turn_ids
        )
