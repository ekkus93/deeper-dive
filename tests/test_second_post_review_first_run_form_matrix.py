"""Dirty navigation matrix for first-run setup inputs and selectors."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import SetupMode, WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize(
    ("step", "selector"),
    [
        ("provider-config", "setup-provider-name"),
        ("provider-config", "setup-provider-adapter"),
        ("provider-config", "setup-provider-base-url"),
        ("provider-config", "setup-provider-model"),
        ("provider-config", "setup-provider-credential-env"),
        ("provider-config", "setup-provider-network"),
        ("model-test", "setup-role-episode-planning"),
        ("model-test", "setup-role-host-generation"),
        ("model-test", "setup-role-directing"),
        ("model-test", "setup-role-verification"),
        ("speech", "setup-speech-choice"),
        ("speech", "setup-speech-name"),
        ("speech", "setup-speech-adapter"),
        ("speech", "setup-speech-base-url"),
        ("speech", "setup-speech-model"),
        ("speech", "setup-speech-credential-env"),
        ("speech", "setup-speech-network"),
        ("speech", "setup-speech-voices"),
        ("voice-defaults", "setup-host1-voice"),
        ("voice-defaults", "setup-host2-voice"),
        ("voice-defaults", "setup-duration"),
        ("voice-defaults", "setup-research-default"),
    ],
)
def test_first_run_back_cancel_discard_preserves_each_control(
    tmp_path: Path, step: str, selector: str
) -> None:
    asyncio.run(_check_field(tmp_path, step, selector))


async def _check_field(tmp_path: Path, step: str, selector: str) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(
            WizardKind.FIRST_RUN, step, setup_mode=SetupMode.ADVANCED
        )
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()

        widget = wizard.query_one(f"#{selector}")
        if selector in {"setup-host1-voice", "setup-host2-voice"}:
            assert isinstance(widget, Select)
            widget.set_options([("Voice One", "voice-one"), ("Voice Two", "voice-two")])
            await pilot.pause()
        wizard._remember_current_form()
        original = widget.value
        if isinstance(widget, Input):
            widget.value = str(original) + " pending edit"
        else:
            assert isinstance(widget, Select)
            alternatives = {
                "setup-speech-choice": ("deferred", "kitten"),
                "setup-duration": ("30", "10"),
                "setup-research-default": ("off", "aggressive"),
            }
            options = alternatives.get(selector, ("voice-one", "voice-two"))
            widget.value = options[0] if original != options[0] else options[1]
        await pilot.pause()

        pending = widget.value
        assert pending != original
        assert wizard._current_form_dirty()
        assert not wizard.action_back()
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.context.state.current_step == step
        assert widget.value == pending

        wizard.action_cancel_exit_confirmation()
        assert widget.value == pending
        assert wizard._current_form_dirty()
        if step != "model-test":
            assert not wizard.action_continue()
            assert wizard.query_one("#wizard-exit-confirmation").display
            assert widget.value == pending
            wizard.action_cancel_exit_confirmation()

        assert not wizard.action_back()
        wizard.action_confirm_discard_exit()
        await pilot.pause()
        assert widget.value == original
        assert not wizard.query_one("#wizard-exit-confirmation").display
