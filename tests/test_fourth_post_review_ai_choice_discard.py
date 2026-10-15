"""FPR-01: discarding a preset change must not leave a stale AI choice behind."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import choose_option, click, continue_step
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.storage.workspace import WorkspaceManager


def test_discarding_a_preset_restores_the_choice_and_save_keeps_the_durable_provider(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        app._first_run_readiness.close()
        controller = app.provider_controller
        controller.save_provider(
            "local",
            "ollama",
            base_url="http://127.0.0.1:11434",
            default_model="m",
            network_scope="local",
        )
        durable = controller.config_store.path.read_bytes()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard._load_existing_setup()
        await continue_step(pilot, "system-check")
        await continue_step(pilot, "ai-provider")
        choice = wizard.query_one("#setup-ai-choice", Select)
        assert choice.value == "ollama"

        await choose_option(pilot, "#setup-ai-choice", steps_down=2)  # OpenAI
        assert choice.value == "openai"
        await continue_step(pilot, "provider-config")
        assert wizard._current_form_dirty()

        await click(pilot, "#wizard-back")
        assert wizard._exit_confirmation_pending
        await click(pilot, "#wizard-confirm-discard")
        assert wizard.context.state.current_step == "ai-provider"

        # The choice and the fields describe the same (durable) provider again.
        assert wizard.query_one("#setup-provider-adapter", Input).value == "ollama"
        assert choice.value == "ollama"

        await continue_step(pilot, "provider-config")
        assert not wizard._current_form_dirty()
        await click(pilot, "#setup-save-provider")
        assert controller.config_store.path.read_bytes() == durable
        assert controller.config().providers["local"].provider_type == "ollama"


def test_save_provider_refuses_when_choice_and_adapter_disagree(tmp_path: Path) -> None:
    asyncio.run(_mismatch(tmp_path))


async def _mismatch(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        app._first_run_readiness.close()
        controller = app.provider_controller
        controller.save_provider(
            "local",
            "ollama",
            base_url="http://127.0.0.1:11434",
            default_model="m",
            network_scope="local",
        )
        durable = controller.config_store.path.read_bytes()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard._load_existing_setup()
        await continue_step(pilot, "system-check")
        await continue_step(pilot, "ai-provider")
        await continue_step(pilot, "provider-config")
        # Force the inconsistent state the defect produced: fields say ollama,
        # the choice says openai.
        with wizard.query_one("#setup-ai-choice", Select).prevent(Select.Changed):
            wizard.query_one("#setup-ai-choice", Select).value = "openai"
        await click(pilot, "#setup-save-provider")
        assert controller.config_store.path.read_bytes() == durable
        assert "disagree" in str(wizard.query_one("#wizard-status").render())


def test_preset_never_becomes_the_clean_baseline_when_a_differing_baseline_exists(
    tmp_path: Path,
) -> None:
    asyncio.run(_secondary(tmp_path))


async def _secondary(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        await continue_step(pilot, "system-check")
        await continue_step(pilot, "ai-provider")
        await continue_step(pilot, "provider-config")
        # A baseline that differs from the widgets (an earlier edit or rehydrate).
        stale = tuple((key, value + "x") for key, value in wizard._editable_snapshot())
        wizard._form_baselines["provider-config"] = stale
        wizard._preset_baseline_steps.discard("provider-config")
        wizard._capture_preset_baseline("provider-config")
        assert "provider-config" in wizard._preset_baseline_steps
        assert wizard._form_baselines["provider-config"] == stale
