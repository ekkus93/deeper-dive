"""Recommended role presets must not silently replace unsaved first-run edits."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Button, Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.model_roles import ModelRole
from deeper_dive.storage.workspace import WorkspaceManager


def test_recommended_roles_require_explicit_decision_for_dirty_form(tmp_path: Path) -> None:
    asyncio.run(_recommended_roles_require_explicit_decision(tmp_path))


async def _recommended_roles_require_explicit_decision(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.action_continue()
        wizard.action_continue()
        wizard.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        wizard.action_continue()
        wizard.query_one("#setup-provider-name", Input).value = "fixture"
        wizard.query_one("#setup-provider-adapter", Input).value = "fake"
        wizard.query_one("#setup-provider-model", Input).value = "fake-v1"
        wizard.query_one("#setup-provider-network", Input).value = "local"
        await pilot.pause()
        assert wizard.action_save_provider()
        wizard.action_continue()
        assert wizard.context.state.current_step == "model-test"

        role = wizard.query_one("#setup-role-directing", Input)
        role.value = "fixture:unsaved-custom"
        assert wizard._current_form_dirty()
        before = dict(app.provider_controller.config().defaults)
        wizard.action_recommended_roles()
        assert wizard._exit_confirmation_pending
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert role.value == "fixture:unsaved-custom"
        assert app.provider_controller.config().defaults == before
        assert "apply recommendations" in str(
            wizard.query_one("#wizard-confirm-discard", Button).label
        )

        wizard.action_cancel_exit_confirmation()
        assert not wizard._exit_confirmation_pending
        assert role.value == "fixture:unsaved-custom"
        assert app.provider_controller.config().defaults == before

        wizard.action_recommended_roles()
        wizard.action_confirm_discard_exit()
        assert not wizard._exit_confirmation_pending
        assert role.value == "fixture:fake-v1"
        for required in (
            ModelRole.EPISODE_PLANNING,
            ModelRole.HOST_GENERATION,
            ModelRole.DIRECTING,
            ModelRole.VERIFICATION,
        ):
            assert app.provider_controller.config().defaults[required.value] == "fixture:fake-v1"

        role.value = "fixture:another-unsaved"
        wizard.action_recommended_roles()
        assert wizard._exit_confirmation_pending
        wizard.action_confirm_save_exit()
        assert not wizard._exit_confirmation_pending
        assert role.value == "fixture:fake-v1"
        assert app.provider_controller.config().defaults["directing"] == "fixture:fake-v1"
