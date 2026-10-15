"""FPR-09: an external config change must not leave earlier steps looking edited."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import click
from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.settings_screen import SettingsController
from deeper_dive.storage.workspace import WorkspaceManager


def test_back_after_an_external_speech_change_shows_the_new_values_without_a_prompt(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        controller = app.provider_controller
        controller.save_provider("speech", "fake-tts", voices=("voice-a", "voice-b"))
        SettingsController(controller).set_defaults(
            {
                "tts_provider": "speech",
                "tts_voice": "voice-a",
                "quick_deep_dive_duration_minutes": "20",
                "research_policy": "useful",
            }
        )
        # Reaching the speech step through the model-test prerequisites needs a live
        # provider, so the position is seeded; everything after is real input.
        wizard._load_existing_setup()
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "speech")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()
        assert not wizard._current_form_dirty()

        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "voice-defaults")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()

        # Another surface (the Providers screen) changes the saved speech provider.
        controller.save_provider("speech", "fake-tts", voices=("voice-a", "voice-x"))
        wizard.on_screen_resume()  # what Textual calls when the wizard is shown again
        await pilot.pause()

        await click(pilot, "#wizard-back")
        assert not wizard._exit_confirmation_pending, "false unsaved-changes prompt"
        assert wizard.context.state.current_step == "speech"
        assert wizard.query_one("#setup-speech-voices", Input).value == "voice-a,voice-x"
        await pilot.pause()
        assert not wizard._current_form_dirty()
