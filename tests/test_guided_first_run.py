"""Deterministic first-run provider/model workflow acceptance."""

from __future__ import annotations

import asyncio
from pathlib import Path

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
        assert "Saved provider fixture" in str(
            screen.query_one("#wizard-status", Static).render()
        )

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
