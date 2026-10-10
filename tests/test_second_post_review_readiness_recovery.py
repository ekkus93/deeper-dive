"""Late readiness callbacks must not discard first-run form edits."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize(
    ("step", "selector", "changed"),
    (
        ("provider-config", "#setup-provider-name", "unsaved-provider"),
        ("model-test", "#setup-role-episode-planning", "unsaved:model"),
        ("speech", "#setup-speech-name", "unsaved-speech"),
    ),
)
def test_late_readiness_recovery_preserves_unsaved_form(
    tmp_path: Path, step: str, selector: str, changed: str
) -> None:
    asyncio.run(_verify_late_readiness(tmp_path, step, selector, changed))


async def _verify_late_readiness(
    tmp_path: Path, step: str, selector: str, changed: str
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, step)
        wizard._sync_text()
        wizard._sync_setup_controls()
        wizard._remember_current_form()

        field = wizard.query_one(selector, Input)
        original = field.value
        field.value = changed
        assert wizard._current_form_dirty()

        wizard.completion_probe = lambda key: key != "welcome"
        assert wizard.navigator.recovered_state().current_step == "welcome"
        wizard._runtime_readiness_updated()

        assert wizard.context.state.current_step == step
        assert field.value == changed
        assert wizard._current_form_dirty()
        assert "unsaved setup edits remain" in str(
            wizard.query_one("#wizard-status", Static).render()
        )

        field.value = original
        assert not wizard._current_form_dirty()
        wizard._runtime_readiness_updated()
        assert wizard.context.state.current_step == "welcome"
