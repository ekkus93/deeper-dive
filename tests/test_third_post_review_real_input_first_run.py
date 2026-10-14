"""TPR-18: first-run provider editing and dirty Back driven only by real input."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import click, continue_step, type_into
from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.storage.workspace import WorkspaceManager


def test_typed_provider_edit_prompts_on_back_and_discard_keeps_config(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        await continue_step(pilot, "system-check")
        await continue_step(pilot, "ai-provider")
        await continue_step(pilot, "provider-config")
        config_path = app.provider_controller.config_store.path
        before = config_path.read_bytes() if config_path.exists() else None

        name = wizard.query_one("#setup-provider-name", Input)
        await type_into(pilot, "#setup-provider-name", "typed-provider")
        assert wizard._current_form_dirty()

        await click(pilot, "#wizard-back")
        assert wizard._exit_confirmation_pending
        assert wizard.context.state.current_step == "provider-config"
        await click(pilot, "#wizard-confirm-discard")

        assert not wizard._exit_confirmation_pending
        assert wizard.context.state.current_step == "ai-provider"
        assert name.value != "typed-provider"
        after = config_path.read_bytes() if config_path.exists() else None
        assert after == before
