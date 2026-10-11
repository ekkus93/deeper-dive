"""Installed-style Textual episode-library acceptance using the shared production fixture.

The fixture creates real projects, fake-provider generation runs, transcript,
audio and exports. These pilots exercise the UI actions without seeding database
rows or treating the episode configuration's draft state as the run state.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual.widgets import Static

from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController, EpisodeLibraryScreen
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.transcript_review_screen import TranscriptReviewScreen
from deeper_dive.tui import DeeperDiveApp


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_completed_run_library_review_export_duplicate_and_project_isolation(
    two_project_completed_acceptance: Callable[[], Any],
) -> None:
    fixture = two_project_completed_acceptance()
    asyncio.run(_exercise_library(fixture.first, fixture.second))
    asyncio.run(_exercise_library(fixture.second, fixture.first))


async def _exercise_library(completed: Any, foreign: Any) -> None:
    service = completed.service
    project_id = completed.project_id
    episode_id = completed.episode_id
    db = Database(service.workspaces.project_root(project_id) / "project.db")
    episodes = HostEpisodeRepository(db)
    original = episodes.get_episode(episode_id)
    plan = episodes.get_plan(episode_id)
    assert original is not None and plan is not None
    transcript_digest = _sha(completed.transcript_path)
    audio_digest = _sha(completed.audio_path)

    app = DeeperDiveApp(service)
    async with app.run_test(size=(110, 32)) as pilot:
        app.current_project_id = project_id
        app.current_project_name = "Acceptance corpus"
        screen = EpisodeLibraryScreen()
        app.push_screen(screen)
        await pilot.pause()

        listing = str(screen.query_one("#episode-library-list", Static).render())
        assert f"| completed | run {completed.run_id}" in listing
        assert foreign.episode_id not in listing
        items = EpisodeLibraryController.items(app)
        item = next(row for row in items if row.episode.id == episode_id)
        assert item.state == "completed"
        assert item.run is not None and item.run.id == completed.run_id
        assert all(row.episode.project_id == project_id for row in items)

        screen.selected_episode_id = episode_id
        screen.action_export_selected()
        status = str(screen.query_one("#screen-status", Static).render())
        assert "Exported:" in status
        assert _sha(completed.transcript_path) == transcript_digest
        assert _sha(completed.audio_path) == audio_digest

        screen.action_duplicate_selected()
        await pilot.pause()
        duplicate_id = screen.selected_episode_id
        assert duplicate_id is not None and duplicate_id != episode_id
        duplicate = episodes.get_episode(duplicate_id)
        assert duplicate is not None and duplicate.state == "draft"
        assert duplicate.title == f"{original.title} Copy"
        assert EpisodeConfigurationService(db).load_configuration(duplicate_id).host_ids == (
            EpisodeConfigurationService(db).load_configuration(episode_id).host_ids
        )
        duplicate_item = next(
            row for row in EpisodeLibraryController.items(app)
            if row.episode.id == duplicate_id
        )
        assert duplicate_item.run is None
        assert duplicate_item.state == "draft"

        assert episodes.get_episode(episode_id) == original
        assert episodes.get_plan(episode_id) == plan
        assert service.runs(project_id).get(completed.run_id).state == "completed"

        screen.selected_episode_id = episode_id
        screen.action_open_selected()
        await pilot.pause()
        assert isinstance(app.screen, TranscriptReviewScreen)
        assert app.current_episode_id == episode_id
        assert app.current_run_id == completed.run_id

    assert _sha(completed.transcript_path) == transcript_digest
    assert _sha(completed.audio_path) == audio_digest
