"""SPR-01: discovering models preserves a saved model and unsaved provider edits."""

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
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_model_discovery_preserves_identity_dirty_changes_and_errors(tmp_path: Path) -> None:
    asyncio.run(_check_model_discovery(tmp_path))


async def _check_model_discovery(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    store = UserConfigStore(data_dir / "config.json")
    store.save(
        UserConfig(
            providers={"local": ProviderConfig(provider_type="fake", default_model="stable")}
        )
    )
    original = store.path.read_bytes()
    service = DeeperDiveService(WorkspaceManager(data_dir))
    app = GuidedDeeperDiveApp(service)
    models = ["new-model", "stable"]
    calls: list[tuple[str, ...]] = []

    def discovered() -> tuple[SimpleNamespace, ...]:
        calls.append(tuple(models))
        return tuple(SimpleNamespace(model=name) for name in models)

    provider = SimpleNamespace(models=discovered)
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "provider-config")
        wizard._sync_text()
        wizard._sync_setup_controls()
        wizard.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        wizard.query_one("#setup-provider-name", Input).value = "local"
        wizard.query_one("#setup-provider-adapter", Input).value = "fake"
        model_input = wizard.query_one("#setup-provider-model", Input)
        model_input.value = "stable"
        wizard._remember_current_form()
        picker = wizard.query_one("#setup-model-picker", Select)

        with patch.object(type(app.composition.provider_controller), "llm", return_value=provider):
            wizard.action_discover_models()
            await pilot.pause()
            assert picker.value == "stable"
            assert model_input.value == "stable"
            assert not wizard._current_form_dirty()

            models[:] = ["stable", "new-model"]
            wizard.action_discover_models()
            await pilot.pause()
            assert picker.value == "stable"
            assert model_input.value == "stable"
            assert not wizard._current_form_dirty()

            # A typed unsaved edit cannot be replaced by a discovery refresh.
            model_input.value = "typed-unsaved"
            assert wizard._current_form_dirty()
            wizard.action_discover_models()
            await pilot.pause()
            assert wizard.query_one("#wizard-exit-confirmation").display
            assert model_input.value == "typed-unsaved"
            assert calls == [("new-model", "stable"), ("stable", "new-model")]
            wizard.action_cancel_exit_confirmation()
            assert model_input.value == "typed-unsaved"

            wizard.action_discover_models()
            wizard.action_confirm_discard_exit()
            await pilot.pause()
            assert model_input.value == "stable"
            assert picker.value == "stable"

            # Removing the saved model is reported rather than silently assigning
            # another; the on-disk configured identity must remain unchanged.
            models[:] = ["new-model"]
            wizard.action_discover_models()
            await pilot.pause()
            assert picker.value == Select.BLANK
            assert model_input.value == "stable"
            assert "no longer available" in str(wizard.query_one("#wizard-status", Static).render())

            # Simulate a clean retry after the vanished-model warning, so an
            # actual discovery exception (not just a dirty-form guard) is tested.
            wizard._remember_current_form()

            def failed_discovery() -> None:
                raise OSError("Authorization: Bearer model-discovery-canary")

            with patch.object(provider, "models", side_effect=failed_discovery):
                wizard.action_discover_models()
                await pilot.pause()
            assert "Model discovery failed" in str(
                wizard.query_one("#wizard-status", Static).render()
            )
            assert "model-discovery-canary" not in str(
                wizard.query_one("#wizard-status", Static).render()
            )
            assert "model-discovery-canary" not in (wizard._error_details or "")
            assert model_input.value == "stable"
    assert store.path.read_bytes() == original
