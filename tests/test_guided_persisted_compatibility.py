"""Ensure legacy production artifacts and advanced screens survive the guided TUI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.user_config import UserConfigStore


def test_guided_tui_reopens_completed_legacy_artifacts_and_advanced_routes(
    completed_episode_acceptance: Callable[..., Any],
) -> None:
    """Production-created state must remain readable after a fresh restart."""
    completed = completed_episode_acceptance()
    data_dir = completed.service.workspaces.data_dir
    restored = DeeperDiveService(WorkspaceManager(data_dir))
    project = restored.open_project(completed.project_id)
    assert project is not None
    assert restored.list_sources(project.id)
    assert any(
        restored.list_source_chunks(project.id, source.id)
        for source in restored.list_sources(project.id)
    )
    assert completed.transcript_path.is_file()
    assert completed.audio_path.is_file()

    config = UserConfigStore(data_dir / "config.json").load()
    assert config.providers["fake"].default_model == "fake-v1"
    assert config.providers["speech"].provider_type == "fake-tts"

    app = GuidedDeeperDiveApp(restored)
    database = app.composition.database_for_project(project.id)
    persisted = EpisodeConfigurationService(database).load_configuration(
        completed.episode_id
    )
    assert persisted.title
    assert AudioTimelineRepository(database).get(completed.episode_id) is not None
    run = restored.runs(project.id).get(completed.run_id)
    assert run is not None and run.state == "completed"
    assert run.episode_id == completed.episode_id

    async def verify_tui() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            app.current_project_id = project.id
            app.current_episode_id = completed.episode_id
            app.current_run_id = completed.run_id
            assert {turn.id for turn in TranscriptReviewController().turns(app)} == set(
                completed.turn_ids
            )
            item = next(
                item
                for item in EpisodeLibraryController.items(app)
                if item.episode.id == completed.episode_id
            )
            assert item.run is not None and item.run.id == completed.run_id
            exported = EpisodeLibraryController.export(app, item)
            assert exported.transcript.is_file()
            assert exported.audio is not None and exported.audio.is_file()
            assert EpisodeLibraryController.audio_path(app, item).is_file()

            for destination, screen_id in (
                ("sources", "screen-sources"),
                ("research", "screen-research"),
                ("hosts", "screen-hosts"),
                ("episode", "screen-episode"),
                ("providers", "screen-providers"),
                ("settings", "screen-settings"),
            ):
                app.action_navigate(destination)
                await pilot.pause()
                assert app.screen.id == screen_id, destination

            app.action_navigate("library")
            await pilot.pause()
            assert app.screen.id == "screen-library"
            assert any(
                item.episode.id == completed.episode_id
                for item in EpisodeLibraryController.items(app)
            )

    asyncio.run(verify_tui())
