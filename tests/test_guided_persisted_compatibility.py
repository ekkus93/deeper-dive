"""Persisted guided-workflow compatibility after reconstructing production services."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Button, Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.model_roles import ModelRole
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_generated_guided_episode_reopens_and_exports_in_fresh_app(tmp_path: Path) -> None:
    asyncio.run(_generated_guided_episode_reopens(tmp_path))


async def _generated_guided_episode_reopens(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "fake": ProviderConfig(
                    provider_type="fake", default_model="fake-v1", network_scope="local"
                ),
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    network_scope="local",
                    voices=("voice-a", "voice-b"),
                ),
            },
            defaults={
                **{
                    role.value: "fake:fake-v1"
                    for role in (
                        ModelRole.EPISODE_PLANNING,
                        ModelRole.HOST_GENERATION,
                        ModelRole.DIRECTING,
                        ModelRole.VERIFICATION,
                    )
                },
                "speech_setup": "configured",
                "tts_provider": "speech",
                "tts_voice": "voice-a",
                "tts_voice_host_1": "voice-a",
                "tts_voice_host_2": "voice-b",
                "research_policy": "useful",
            },
        )
    )
    service = DeeperDiveService(WorkspaceManager(data_dir))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.query_one("#guided-project-name", Input).value = "Persisted project"
        wizard.query_one("#guided-project-topic", Input).value = "How do archives work?"
        wizard.action_create_project()
        project_id = wizard.context.project_id
        assert project_id is not None
        wizard.action_continue()
        wizard.query_one("#guided-source-title", Input).value = "Archive notes"
        wizard.query_one("#guided-source-text", Input).value = "Archives preserve evidence."
        next(button for button in wizard.query(Button) if button.name == "add-source").press()
        await pilot.pause()
        wizard.action_continue()
        wizard.query_one("#guided-research-policy", Select).value = "useful"
        wizard.action_save_research()
        wizard.action_continue()
        wizard.action_create_recommended_hosts()
        wizard.action_save_host_order()
        episode_id = wizard.context.episode_id
        assert episode_id is not None
        wizard.action_continue()
        wizard.query_one("#guided-episode-title", Input).value = "Persisted episode"
        wizard.query_one("#guided-episode-focus", Input).value = "Explain archive evidence"
        wizard.query_one("#guided-episode-duration", Select).value = "10"
        wizard.action_save_episode()
        wizard.action_continue()
        wizard.action_build_plan()
        assert wizard._plan is not None
        wizard.action_continue()
        with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            wizard.action_check_preflight()
            assert wizard._preflight is not None and wizard._preflight.ready
            wizard.action_generate_deep_dive()
        await pilot.pause()
        run_id = wizard.context.run_id
        assert run_id is not None
        app.composition.run_generation(project_id, run_id)
        run = service.runs(project_id).get(run_id)
        assert run is not None and run.state == "completed"

    # Neither the service nor the Textual app is reused after the restart.
    fresh_service = DeeperDiveService(WorkspaceManager(data_dir))
    fresh_app = GuidedDeeperDiveApp(fresh_service)
    async with fresh_app.run_test(size=(80, 24)):
        assert fresh_app.screen.id == "screen-home"
        assert fresh_app.provider_controller.config().providers["fake"].default_model == "fake-v1"
        assert fresh_service.open_project(project_id) is not None
        assert any(
            fresh_service.list_source_chunks(project_id, source.id)
            for source in fresh_service.list_sources(project_id)
        )
        assert fresh_service.hosts(project_id).get_episode(episode_id) is not None
        restored_run = fresh_service.runs(project_id).get(run_id)
        assert restored_run is not None and restored_run.state == "completed"
        assert (
            AudioTimelineRepository(fresh_app.composition.database_for_project(project_id)).get(
                episode_id
            )
            is not None
        )
        fresh_app.current_project_id = project_id
        fresh_app.current_episode_id = episode_id
        fresh_app.current_run_id = run_id
        assert len(TranscriptReviewController().turns(fresh_app)) >= 2
        item = next(
            entry
            for entry in EpisodeLibraryController.items(fresh_app)
            if entry.episode.id == episode_id
        )
        export = EpisodeLibraryController.export(fresh_app, item)
        assert export.audio is not None and export.audio.is_file()
        assert export.transcript.is_file()
