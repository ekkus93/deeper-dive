"""Guided episode, plan, preflight, and generation-start acceptance."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.model_roles import ModelRole
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _service_and_config(tmp_path: Path) -> DeeperDiveService:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "fake": ProviderConfig(
                    provider_type="fake",
                    default_model="fake-v1",
                    network_scope="local",
                ),
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    network_scope="local",
                    voices=("voice-a", "voice-b"),
                ),
            },
            defaults={
                ModelRole.EPISODE_PLANNING.value: "fake:fake-v1",
                ModelRole.HOST_GENERATION.value: "fake:fake-v1",
                ModelRole.DIRECTING.value: "fake:fake-v1",
                ModelRole.VERIFICATION.value: "fake:fake-v1",
                "speech_setup": "configured",
                "tts_provider": "speech",
                "tts_voice": "voice-a",
                "tts_voice_host_1": "voice-a",
                "tts_voice_host_2": "voice-b",
                "quick_deep_dive_duration_minutes": "20",
                "research_policy": "useful",
            },
        )
    )
    return DeeperDiveService(WorkspaceManager(data_dir))


def test_guided_episode_plan_preflight_and_generation_start(tmp_path: Path) -> None:
    asyncio.run(_episode_plan_preflight_and_generation_start(tmp_path))


async def _episode_plan_preflight_and_generation_start(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)

        screen.query_one("#guided-project-name", Input).value = "Oceans"
        screen.query_one("#guided-project-topic", Input).value = "How do oceans store heat?"
        screen.query_one("#guided-project-audience", Select).value = "technical"
        screen.action_create_project()
        project_id = screen.context.project_id
        assert project_id is not None
        screen.action_continue()

        screen.query_one("#guided-source-title", Input).value = "Notes"
        screen.query_one("#guided-source-text", Input).value = "Oceans store and move heat."
        for button in screen.query("Button"):
            if button.name == "add-source":
                button.press()
                break
        await pilot.pause()
        screen.action_continue()

        screen.query_one("#guided-research-policy", Select).value = "useful"
        screen.action_save_research()
        screen.action_continue()

        screen.action_create_recommended_hosts()
        screen.action_save_host_order()
        episode_id = screen.context.episode_id
        assert episode_id is not None
        screen.action_continue()
        assert screen.context.state.current_step == "episode"

        screen.query_one("#guided-episode-title", Input).value = "Ocean Heat"
        screen.query_one("#guided-episode-focus", Input).value = "Where does the heat go?"
        screen.query_one("#guided-episode-duration", Select).value = "10"
        screen.query_one("#guided-episode-audience", Select).value = "technical"
        screen.query_one("#guided-episode-depth", Select).value = "deep"
        screen.query_one("#guided-episode-must-cover", Input).value = "circulation, storage"
        screen.query_one("#guided-episode-avoid", Input).value = "speculation"
        screen.action_save_episode()

        saved = EpisodeConfigurationService(
            app.composition.database_for_project(project_id)
        ).load_configuration(episode_id)
        assert saved.title == "Ocean Heat"
        assert saved.focus == "Where does the heat go?"
        assert saved.target_duration_seconds == 600
        assert saved.must_cover == ("circulation", "storage")
        assert saved.avoid_topics == ("speculation",)

        screen.action_continue()
        assert screen.context.state.current_step == "plan"
        screen.action_build_plan()
        assert screen._plan is not None
        assert screen._plan.target_duration_seconds == 600
        assert "Overview" in str(screen.query_one("#guided-plan-summary", Static).render())

        screen.action_continue()
        assert screen.context.state.current_step == "preflight"
        with patch("deeper_dive.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            screen.action_check_preflight()
            assert screen._preflight is not None
            assert screen._preflight.ready
            assert "Sources: Ready" in str(
                screen.query_one("#guided-preflight-summary", Static).render()
            )
            screen.action_generate_deep_dive()

        assert screen.context.run_id is not None
        run = service.runs(project_id).get(screen.context.run_id)
        assert run is not None
        assert run.episode_id == episode_id
        assert run.state == "pending"


def test_guided_episode_validation_preserves_typed_input(tmp_path: Path) -> None:
    asyncio.run(_episode_validation_preserves_typed_input(tmp_path))


async def _episode_validation_preserves_typed_input(tmp_path: Path) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)
        screen.context.state = screen.context.state.moved_to("episode")
        screen._toggle()
        screen.query_one("#guided-episode-title", Input).value = "Typed title"
        screen.query_one("#guided-episode-focus", Input).value = "Typed focus"
        screen.query_one("#guided-episode-duration", Select).value = "custom"
        screen.query_one("#guided-episode-custom-duration", Input).value = "bad"
        screen.action_save_episode()
        assert screen.query_one("#guided-episode-title", Input).value == "Typed title"
        assert screen.query_one("#guided-episode-focus", Input).value == "Typed focus"
