"""Deterministic first-run provider/model workflow acceptance."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Button, Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.model_roles import ModelRole
from deeper_dive.storage.workspace import WorkspaceManager


def test_first_run_fake_llm_model_roles_and_deferred_speech_survive_restart(
    tmp_path: Path,
) -> None:
    asyncio.run(_check(tmp_path))


async def _check(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        assert isinstance(screen, GuidedFirstRunWizard)

        screen.action_continue()
        screen.action_continue()
        assert screen.context.state.current_step == "ai-provider"

        screen.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        screen.action_continue()
        assert screen.context.state.current_step == "provider-config"

        screen.query_one("#setup-provider-name", Input).value = "fixture"
        screen.query_one("#setup-provider-adapter", Input).value = "fake"
        screen.query_one("#setup-provider-model", Input).value = "fake-v1"
        screen.query_one("#setup-provider-network", Input).value = "local"
        screen.query_one("#setup-save-provider", Button).press()
        await pilot.pause()
        assert "Saved provider fixture" in str(screen.query_one("#wizard-status", Static).render())

        screen.query_one("#setup-test-provider", Button).press()
        await pilot.pause()
        assert "healthy" in str(screen.query_one("#wizard-status", Static).render())
        screen.action_continue()
        assert screen.context.state.current_step == "model-test"

        screen.query_one("#setup-run-model-test", Button).press()
        await pilot.pause()
        assert "succeeded" in str(screen.query_one("#wizard-status", Static).render())
        screen.query_one("#setup-recommended-roles", Button).press()
        await pilot.pause()

        config = app.provider_controller.config()
        for role in (
            ModelRole.EPISODE_PLANNING,
            ModelRole.HOST_GENERATION,
            ModelRole.DIRECTING,
            ModelRole.VERIFICATION,
        ):
            assert config.defaults[role.value] == "fixture:fake-v1"

        screen.action_continue()
        assert screen.context.state.current_step == "speech"
        screen.query_one("#setup-speech-choice", Select).value = "deferred"
        await pilot.pause()
        screen.query_one("#setup-save-speech", Button).press()
        await pilot.pause()
        screen.action_continue()
        assert screen.context.state.current_step == "voice-defaults"

        screen.query_one("#setup-save-defaults", Button).press()
        await pilot.pause()
        screen.action_continue()
        assert screen.context.state.current_step == "ready"
        assert "Language model: Ready" in str(
            screen.query_one("#wizard-step-content", Static).render()
        )

        screen.query_one("#setup-ready-home", Button).press()
        await pilot.pause()
        assert app.screen.id == "screen-home"

    restarted = GuidedDeeperDiveApp(service)
    async with restarted.run_test(size=(100, 30)):
        assert restarted.screen.id == "screen-home"


def test_failed_provider_build_preserves_prior_runtime_and_config(tmp_path: Path) -> None:
    asyncio.run(_failed_provider_build_preserves_prior_runtime_and_config(tmp_path))


async def _failed_provider_build_preserves_prior_runtime_and_config(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        assert isinstance(screen, GuidedFirstRunWizard)
        screen.action_continue()
        screen.action_continue()
        screen.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        screen.action_continue()

        screen.query_one("#setup-provider-name", Input).value = "fixture"
        screen.query_one("#setup-provider-adapter", Input).value = "fake"
        screen.query_one("#setup-provider-model", Input).value = "fake-v1"
        screen.query_one("#setup-provider-network", Input).value = "local"
        await pilot.pause()
        screen.action_save_provider()
        prior_runtime = app.provider_controller.llm("fixture")
        prior_config = app.provider_controller.config()

        screen.query_one("#setup-provider-adapter", Input).value = "openai"
        screen.query_one("#setup-provider-model", Input).value = "gpt-test"
        screen.query_one(
            "#setup-provider-credential-env", Input
        ).value = "DEEPER_DIVE_MISSING_TEST_CREDENTIAL"
        screen.query_one("#setup-provider-network", Input).value = "remote"
        await pilot.pause()
        screen.action_save_provider()

        status = str(screen.query_one("#wizard-status", Static).render())
        assert "Provider save failed" in status
        assert app.provider_controller.config() == prior_config
        assert app.provider_controller.llm("fixture") is prior_runtime
        assert screen.query_one("#setup-provider-model", Input).value == "gpt-test"


def test_first_run_fake_tts_voice_preview_and_ready_restart(tmp_path: Path) -> None:
    with patch("deeper_dive.first_run.shutil.which", return_value="/usr/bin/ffmpeg"):
        asyncio.run(_fake_tts_voice_preview_and_ready_restart(tmp_path))


async def _fake_tts_voice_preview_and_ready_restart(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        assert isinstance(screen, GuidedFirstRunWizard)

        screen.action_continue()
        screen.action_continue()
        screen.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        screen.action_continue()
        screen.query_one("#setup-provider-name", Input).value = "fixture"
        screen.query_one("#setup-provider-adapter", Input).value = "fake"
        screen.query_one("#setup-provider-model", Input).value = "fake-v1"
        screen.query_one("#setup-provider-network", Input).value = "local"
        await pilot.pause()
        screen.action_save_provider()
        screen.action_continue()
        screen.action_run_model_test()
        screen.action_recommended_roles()
        screen.action_continue()
        assert screen.context.state.current_step == "speech"

        screen.query_one("#setup-speech-choice", Select).value = "advanced"
        await pilot.pause()
        screen.query_one("#setup-speech-name", Input).value = "speech"
        screen.query_one("#setup-speech-adapter", Input).value = "fake-tts"
        screen.query_one("#setup-speech-network", Input).value = "local"
        screen.query_one("#setup-speech-voices", Input).value = "voice-a,voice-b"
        await pilot.pause()
        assert screen.query_one("#setup-speech-voices", Input).display
        screen.action_save_speech()
        screen.action_continue()
        assert screen.context.state.current_step == "voice-defaults"

        screen.action_discover_voices()
        assert screen.query_one("#setup-host1-voice", Select).value == "voice-a"
        assert screen.query_one("#setup-host2-voice", Select).value == "voice-b"
        screen.action_preview_voice()
        status = str(screen.query_one("#wizard-status", Static).render())
        assert "Voice preview synthesized through speech" in status
        assert any((tmp_path / "data" / "voice-previews").iterdir())

        screen.action_save_defaults()
        config = app.provider_controller.config()
        assert config.defaults["tts_provider"] == "speech"
        assert config.defaults["tts_voice"] == "voice-a"
        assert config.defaults["tts_voice_host_1"] == "voice-a"
        assert config.defaults["tts_voice_host_2"] == "voice-b"
        screen.action_continue()
        assert screen.context.state.current_step == "ready"
        assert "Speech/audio: Ready" in str(
            screen.query_one("#wizard-step-content", Static).render()
        )

    restarted = GuidedDeeperDiveApp(service)
    async with restarted.run_test(size=(100, 30)):
        assert restarted.screen.id == "screen-home"

    restarted.provider_controller.remove_provider("fixture")
    invalidated = GuidedDeeperDiveApp(service)
    async with invalidated.run_test(size=(100, 30)) as pilot:
        assert invalidated.screen.id == "screen-home"
        await pilot.pause()
        resume_setup = invalidated.screen.query_one("#action-resume-setup", Button)
        assert resume_setup.display
        resume_setup.press()
        await pilot.pause()
        assert invalidated.screen.id == "screen-wizard-first-run"


def test_first_run_model_test_failure_and_retry(tmp_path: Path) -> None:
    asyncio.run(_model_test_failure_and_retry(tmp_path))


async def _model_test_failure_and_retry(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        assert isinstance(screen, GuidedFirstRunWizard)
        screen.action_continue()
        screen.action_continue()
        screen.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        screen.action_continue()
        screen.query_one("#setup-provider-name", Input).value = "fixture"
        screen.query_one("#setup-provider-adapter", Input).value = "fake"
        screen.query_one("#setup-provider-model", Input).value = "fake-v1"
        screen.query_one("#setup-provider-network", Input).value = "local"
        await pilot.pause()
        screen.action_save_provider()
        screen.action_continue()
        provider = app.provider_controller.llm("fixture")
        with patch.object(provider, "generate", side_effect=RuntimeError("provider unavailable")):
            screen.action_run_model_test()
            assert "Model test failed" in str(screen.query_one("#wizard-status", Static).render())
            assert "provider unavailable" not in str(
                screen.query_one("#wizard-status", Static).render()
            )
            screen.action_help()
            assert "Details: provider unavailable" in str(
                screen.query_one("#wizard-status", Static).render()
            )
            assert screen._model_test_identity is None
            screen.action_continue()
            assert screen.context.state.current_step == "model-test"
        screen.action_run_model_test()
        assert "Model test succeeded" in str(screen.query_one("#wizard-status", Static).render())


def test_first_run_save_exit_resumes_durable_partial_provider_setup(tmp_path: Path) -> None:
    asyncio.run(_first_run_save_exit_resumes_durable_partial_provider_setup(tmp_path))


async def _first_run_save_exit_resumes_durable_partial_provider_setup(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        assert isinstance(screen, GuidedFirstRunWizard)
        screen.action_continue()
        screen.action_continue()
        screen.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        screen.action_continue()
        assert screen.context.state.current_step == "provider-config"
        screen.query_one("#setup-provider-name", Input).value = "fixture"
        screen.query_one("#setup-provider-adapter", Input).value = "fake"
        screen.query_one("#setup-provider-model", Input).value = "fake-v1"
        screen.query_one("#setup-provider-network", Input).value = "local"
        await pilot.pause()
        screen.action_save_provider()
        screen.action_save_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"
        assert (tmp_path / "data" / "guided-first-run-draft.json").is_file()

    restarted = GuidedDeeperDiveApp(service)
    async with restarted.run_test(size=(100, 30)) as pilot:
        assert restarted.screen.id == "screen-home"
        resume = restarted.screen.query_one("#action-resume-setup", Button)
        assert resume.display
        resume.press()
        await pilot.pause()
        screen = restarted.screen
        assert isinstance(screen, GuidedFirstRunWizard)
        assert screen.context.state.current_step == "provider-config"
        provider = screen.context.composition.provider_controller.config().providers["fixture"]
        assert provider.default_model == "fake-v1"
        screen.action_continue()
        assert screen.context.state.current_step == "model-test"
