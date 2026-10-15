"""Model discovery cannot replace an unsaved first-run provider model."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_transitions import Transition, TransitionKind


def test_discovery_requires_save_discard_or_cancel_for_dirty_provider(tmp_path: Path) -> None:
    asyncio.run(_discovery_requires_explicit_choice(tmp_path))


async def _discovery_requires_explicit_choice(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "provider-config")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()
        field = wizard.query_one("#setup-provider-model", Input)
        original = field.value
        field.value = "pending-unsaved-model"
        assert wizard._current_form_dirty()

        models_calls: list[str] = []
        fake_provider = SimpleNamespace(
            models=lambda: models_calls.append("called")
            or (SimpleNamespace(model="model-from-discovery"),)
        )
        with (
            patch.object(wizard, "_selected_llm_name", return_value="configured-llm"),
            patch.object(
                type(app.composition.provider_controller), "llm", return_value=fake_provider
            ),
        ):
            wizard.action_discover_models()
            await pilot.pause()
            assert wizard.query_one("#wizard-exit-confirmation").display
            assert wizard._pending_transition == Transition(TransitionKind.DISCOVER_MODELS)
            assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")
            assert "discover models" in str(wizard.query_one("#wizard-status", Static).render())
            assert models_calls == []
            assert field.value == "pending-unsaved-model"

            wizard.action_cancel_exit_confirmation()
            assert field.value == "pending-unsaved-model"
            assert wizard._current_form_dirty()
            wizard.action_discover_models()
            assert wizard.query_one("#wizard-exit-confirmation").display
            wizard.action_confirm_discard_exit()
            await pilot.pause()

            assert models_calls == ["called"]
            picker = wizard.query_one("#setup-model-picker", Select)
            assert picker.value == "model-from-discovery"
            assert field.value == "model-from-discovery"
            assert not wizard.query_one("#wizard-exit-confirmation").display
            assert original != field.value
