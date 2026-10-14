"""TPR-08: a changed AI preset is an unsaved edit, never silently the clean baseline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager


def test_preset_change_is_dirty_prompts_on_back_and_discard_restores_durable(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        controller = app.provider_controller
        controller.save_provider(
            "local",
            "ollama",
            base_url="http://127.0.0.1:11434",
            default_model="m",
            network_scope="local",
        )
        durable = controller.config_store.path.read_bytes()
        wizard._load_existing_setup()
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "ai-provider")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()

        wizard.query_one("#setup-ai-choice", Select).value = "openai"
        await pilot.pause()
        assert wizard.query_one("#setup-provider-name", Input).value == "openai"

        assert wizard.action_continue()
        await pilot.pause()
        assert wizard.context.state.current_step == "provider-config"
        # The preset values differ from the stored Ollama provider: unsaved edit.
        assert wizard._current_form_dirty()

        wizard.action_back()
        await pilot.pause()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_discard_exit()
        await pilot.pause()

        assert wizard.query_one("#setup-provider-name", Input).value == "local"
        assert wizard.query_one("#setup-provider-adapter", Input).value == "ollama"
        assert controller.config_store.path.read_bytes() == durable


def test_preset_change_save_persists_the_new_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key-000000000000")
    asyncio.run(_save_path(tmp_path))


async def _save_path(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        controller = app.provider_controller
        controller.save_provider(
            "local",
            "ollama",
            base_url="http://127.0.0.1:11434",
            default_model="m",
            network_scope="local",
        )
        wizard._load_existing_setup()
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "ai-provider")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()

        wizard.query_one("#setup-ai-choice", Select).value = "openai"
        await pilot.pause()
        assert wizard.action_continue()
        await pilot.pause()
        assert wizard._current_form_dirty()

        wizard.action_back()
        await pilot.pause()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        await pilot.pause()

        providers = controller.config().providers
        assert "openai" in providers
        assert providers["openai"].provider_type == "openai"
        assert not wizard._exit_confirmation_pending
