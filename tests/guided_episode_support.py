"""Guided episode, plan, preflight, and generation-start acceptance."""

from __future__ import annotations

from pathlib import Path

from textual.pilot import Pilot
from textual.widgets import Button, Input, Select

from deeper_dive.application.service import DeeperDiveService
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


async def _prepare_to_plan(
    screen: GuidedEpisodeWizard,
    pilot: Pilot[None],
) -> tuple[str, str]:
    screen.query_one("#guided-project-name", Input).value = "Regression"
    screen.query_one("#guided-project-topic", Input).value = "What should we understand?"
    screen.action_create_project()
    project_id = screen.context.project_id
    assert project_id is not None
    screen.action_continue()

    screen.query_one("#guided-source-title", Input).value = "Notes"
    screen.query_one("#guided-source-text", Input).value = "Evidence for the regression."
    for button in screen.query(Button):
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

    screen.query_one("#guided-episode-title", Input).value = "Regression Episode"
    screen.query_one("#guided-episode-focus", Input).value = "Explain the evidence"
    screen.query_one("#guided-episode-duration", Select).value = "10"
    screen.action_save_episode()
    screen.action_continue()
    assert screen.context.state.current_step == "plan"
    return project_id, episode_id
