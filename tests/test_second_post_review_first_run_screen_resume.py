"""Re-entering first-run must reload durable settings without losing pending edits."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager


def test_setup_screen_resume_refreshes_clean_state_but_preserves_dirty_edit(tmp_path: Path) -> None:
    asyncio.run(_exercise_screen_resume(tmp_path))


async def _exercise_screen_resume(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        # Isolate the rehydration contract from the background health network.
        app._first_run_readiness.close()
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "provider-config")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()

        controller = app.composition.provider_controller
        controller.save_provider(
            "resume-fixture",
            "ollama",
            base_url="http://127.0.0.1:11434",
            default_model="durable-first",
            network_scope="local",
        )
        with patch.object(wizard, "_request_runtime_readiness"):
            wizard.on_screen_resume()
            await pilot.pause()
        model = wizard.query_one("#setup-provider-model", Input)
        assert model.value == "durable-first"
        assert not wizard._current_form_dirty()
        assert wizard._llm_provider_name == "resume-fixture"

        # Adding an alphabetically earlier LLM must not silently reselect it
        # when this wizard has an existing, still-valid provider identity.
        controller.save_provider(
            "aaa-alternate",
            "ollama",
            base_url="http://127.0.0.1:11434",
            default_model="unrelated-model",
            network_scope="local",
        )

        # An external Settings update must refresh a clean visible provider.
        controller.save_provider(
            "resume-fixture",
            "ollama",
            base_url="http://127.0.0.1:11434",
            default_model="durable-second",
            network_scope="local",
        )
        # Exercise the real installed Textual screen transition, not only
        # a direct call to the resume hook.
        with patch.object(wizard, "_request_runtime_readiness"):
            app.action_navigate("home")
            await pilot.pause()
            assert app.screen is not wizard
            app.action_navigate("setup")
            await pilot.pause()
            assert app.screen is wizard
        assert model.value == "durable-second"
        assert wizard._llm_provider_name == "resume-fixture"
        assert not wizard._current_form_dirty()

        # A further external write must not replace typed, not-yet-saved input.
        model.value = "unsaved-model-selection"
        assert wizard._current_form_dirty()
        controller.save_provider(
            "resume-fixture",
            "ollama",
            base_url="http://127.0.0.1:11434",
            default_model="durable-third",
            network_scope="local",
        )
        with patch.object(wizard, "_request_runtime_readiness"):
            wizard.on_screen_resume()
            await pilot.pause()
        assert wizard.context.state.current_step == "provider-config"
        assert model.value == "unsaved-model-selection"
        assert wizard._current_form_dirty()
        assert "Unsaved setup edits remain" in str(
            wizard.query_one("#wizard-status", Static).render()
        )
        assert controller.config().providers["resume-fixture"].default_model == "durable-third"
