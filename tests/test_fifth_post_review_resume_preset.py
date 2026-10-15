"""5PR-05: leaving the first-run wizard and coming back must not discard an unsaved AI preset."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import choose_option, click, continue_step
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_unsaved_ai_preset_survives_leaving_and_returning(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    data = tmp_path / "data"
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(data)))
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
        wizard = app.screen
        # A fresh first-run wizard starts before any provider exists; load the one saved
        # above (the same call Resume makes) and walk the rest with real clicks.
        wizard._load_existing_setup()
        await continue_step(pilot, "system-check")
        await continue_step(pilot, "ai-provider")
        await choose_option(pilot, "#setup-ai-choice", steps_down=2)
        picked = wizard.query_one("#setup-ai-choice", Select).value
        assert picked != "ollama"
        picked_adapter = wizard.query_one("#setup-provider-adapter", Input).value
        durable_before = controller.config().providers["local"]

        # Leaving the wizard and returning to it is what Textual reports as a screen
        # resume; Home is the screen the user would actually visit.
        app.push_screen("home")
        await pilot.pause()
        app.pop_screen()
        await pilot.pause()
        await pilot.pause()

        assert wizard.query_one("#setup-ai-choice", Select).value == picked
        assert wizard.query_one("#setup-provider-adapter", Input).value == picked_adapter

        await click(pilot, "#wizard-continue")
        assert wizard.context.state.current_step == "provider-config"
        assert wizard._current_form_dirty()  # the preset is unsaved, and shown as such
        await click(pilot, "#wizard-back")
        assert wizard._exit_confirmation_pending
        await click(pilot, "#wizard-confirm-discard")

        assert wizard.query_one("#setup-ai-choice", Select).value == "ollama"
        assert wizard.query_one("#setup-provider-adapter", Input).value == "ollama"
        assert wizard.query_one("#setup-provider-model", Input).value == "m"
        assert controller.config().providers["local"] == durable_before


def test_preset_survives_leaving_from_the_provider_config_step(tmp_path: Path) -> None:
    """6PR-10: the spec's exact path (Continue to provider-config, leave, return), by bytes."""

    asyncio.run(_provider_config_path(tmp_path))


async def _provider_config_path(tmp_path: Path) -> None:
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
        durable_bytes = controller.config_store.path.read_bytes()
        wizard = app.screen
        wizard._load_existing_setup()
        await continue_step(pilot, "system-check")
        await continue_step(pilot, "ai-provider")
        await choose_option(pilot, "#setup-ai-choice", steps_down=2)
        picked = wizard.query_one("#setup-ai-choice", Select).value
        await click(pilot, "#wizard-continue")
        assert wizard.context.state.current_step == "provider-config"
        adapter = wizard.query_one("#setup-provider-adapter", Input).value
        assert wizard._current_form_dirty()

        app.push_screen("home")
        await pilot.pause()
        app.pop_screen()
        await pilot.pause()
        await pilot.pause()

        assert wizard.context.state.current_step == "provider-config"
        assert wizard.query_one("#setup-ai-choice", Select).value == picked
        assert wizard.query_one("#setup-provider-adapter", Input).value == adapter
        assert wizard._current_form_dirty()
        assert controller.config_store.path.read_bytes() == durable_bytes
