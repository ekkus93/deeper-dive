from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryScreen
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def test_library_preserves_independent_run_states_and_actions(tmp_path: Path) -> None:
    asyncio.run(_library_workflow(tmp_path))


async def _library_workflow(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Library")
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episodes = EpisodeConfigurationService(database, clock=service.clock)
    paused = episodes.create(project.id, EpisodeConfiguration(title="Paused episode"))
    failed = episodes.create(project.id, EpisodeConfiguration(title="Failed episode"))
    complete = episodes.create(project.id, EpisodeConfiguration(title="Complete episode"))
    timestamp = format_timestamp(service.clock.now())
    for episode, state in ((paused, "paused"), (failed, "failed"), (complete, "completed")):
        service.runs(project.id).create(
            GenerationRunRecord(
                id=str(new_run_id()),
                episode_id=episode.id,
                stage="conversation" if state != "completed" else "export",
                state=state,
                created_at=timestamp,
                modified_at=timestamp,
                pause_requested=state == "paused",
                failure_code="fake_failure" if state == "failed" else None,
            )
        )

    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        screen = EpisodeLibraryScreen()
        app.push_screen(screen)
        await pilot.pause()
        listing = str(screen.query_one("#episode-library-list", Static).render())
        assert "Paused episode | paused" in listing
        assert "Failed episode | failed" in listing
        assert "Complete episode | completed" in listing

        screen.selected_episode_id = paused.id
        screen.action_duplicate_selected()
        await pilot.pause()
        listing = str(screen.query_one("#episode-library-list", Static).render())
        assert "Paused episode Copy | draft" in listing
        assert len(service.hosts(project.id).list_episodes(project.id)) == 4

        screen.action_export_selected()
        assert "output" in str(screen.query_one("#screen-status", Static).render())

        screen.action_request_delete()
        screen.action_cancel_delete()
        assert len(service.hosts(project.id).list_episodes(project.id)) == 4
        screen.action_request_delete()
        screen.action_confirm_delete()
        await pilot.pause()
        assert len(service.hosts(project.id).list_episodes(project.id)) == 3

        screen.action_new_episode()
        await pilot.pause()
        assert app.screen.id == "screen-episode"
        assert app.current_episode_id is None
        assert app.current_run_id is None


def _service(tmp_path: Path) -> DeeperDiveService:
    return DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)),
    )
