"""Regression for unsaved speech setup on preset selection."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager


def test_dirty_speech_preset_switch_requires_confirmation(tmp_path: Path) -> None:
    asyncio.run(_verify(tmp_path))


async def _verify(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "speech")
        wizard._sync_text()
        wizard._sync_setup_controls()
        wizard._remember_current_form()
        picker = wizard.query_one("#setup-speech-choice", Select)
        initial = picker.value
        assert isinstance(initial, str)
        name = wizard.query_one("#setup-speech-name", Input)
        name.value = "Unsaved speech name"
        await pilot.pause()
        choice = "openai-tts" if initial != "openai-tts" else "kitten"
        picker.value = choice
        await pilot.pause()
        assert picker.value == initial
        assert name.value == "Unsaved speech name"
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_cancel_exit_confirmation()
        assert picker.value == initial
        assert name.value == "Unsaved speech name"
        picker.value = choice
        await pilot.pause()
        wizard.action_confirm_discard_exit()
        await pilot.pause()
        assert picker.value == choice
        assert name.value != "Unsaved speech name"
