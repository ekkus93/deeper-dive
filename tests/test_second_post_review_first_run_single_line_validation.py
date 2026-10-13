"""SPR-04: first-run rejects model and role control bytes before trimming."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager


def test_first_run_rejects_untrimmed_control_bytes_without_publishing(tmp_path: Path) -> None:
    asyncio.run(_exercise_first_run_validation(tmp_path))


async def _exercise_first_run_validation(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.action_continue()
        wizard.action_continue()
        wizard.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        wizard.action_continue()
        assert wizard.context.state.current_step == "provider-config"

        wizard.query_one("#setup-provider-name", Input).value = "fixture"
        wizard.query_one("#setup-provider-adapter", Input).value = "fake"
        wizard.query_one("#setup-provider-model", Input).value = "safe-model\x1b[31m"
        assert not wizard.action_save_provider()
        assert "single-line" in str(wizard.query_one("#wizard-status", Static).render())
        assert "fixture" not in app.provider_controller.config().providers

        wizard.query_one("#setup-provider-model", Input).value = "safe-model"
        assert wizard.action_save_provider()
        assert app.provider_controller.config().providers["fixture"].default_model == "safe-model"

        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "model-test")
        wizard._sync_text()
        wizard._sync_setup_controls()
        for selector in (
            "#setup-role-episode-planning",
            "#setup-role-host-generation",
            "#setup-role-directing",
            "#setup-role-verification",
        ):
            wizard.query_one(selector, Input).value = "fixture:safe-model"
        wizard.query_one("#setup-role-host-generation", Input).value = "fixture:safe-model\r"
        original = app.provider_controller.config_store.path.read_bytes()
        assert not wizard.action_save_roles()
        assert "single-line" in str(wizard.query_one("#wizard-status", Static).render())
        assert app.provider_controller.config_store.path.read_bytes() == original
        assert "host_generation" not in app.provider_controller.config().defaults
