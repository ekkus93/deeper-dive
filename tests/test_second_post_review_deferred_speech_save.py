"""Deferred speech writes must use first-run's loss-safe TUI save contract."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.settings_screen import SettingsController
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("via_confirmation", (False, True))
def test_deferred_speech_write_failure_preserves_wizard_and_allows_retry(
    tmp_path: Path, via_confirmation: bool
) -> None:
    asyncio.run(_deferred_speech_write_failure(tmp_path, via_confirmation))


async def _deferred_speech_write_failure(tmp_path: Path, via_confirmation: bool) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "speech")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()
        selector = wizard.query_one("#setup-speech-choice", Select)
        selector.value = "deferred"
        await pilot.pause()
        assert wizard._current_form_dirty()
        config_store = app.composition.provider_controller.config_store
        before = config_store.path.read_bytes() if config_store.path.exists() else None
        identity = wizard._tts_provider_name

        def fail_write(_controller: SettingsController, _values: object) -> None:
            try:
                raise ValueError("Authorization: Bearer deferred-speech-canary")
            except ValueError as cause:
                raise OSError("simulated durable write failure") from cause

        with patch.object(SettingsController, "set_defaults", fail_write):
            if via_confirmation:
                wizard.action_save_exit()
                assert wizard.query_one("#wizard-exit-confirmation").display
                wizard.action_confirm_save_exit()
            else:
                assert wizard.action_save_speech() is False
            await pilot.pause()

        assert app.screen is wizard
        assert wizard.context.state.current_step == "speech"
        assert selector.value == "deferred"
        assert wizard._current_form_dirty()
        assert wizard._tts_provider_name == identity
        assert not wizard.save_exit_requested
        assert not wizard.query_one("#wizard-exit-confirmation").display
        assert (config_store.path.read_bytes() if config_store.path.exists() else None) == before
        status = str(wizard.query_one("#wizard-status", Static).render())
        assert "Speech configuration failed" in status
        assert "deferred-speech-canary" not in status
        assert "deferred-speech-canary" not in (wizard._error_details or "")

        # Retry against the real production SettingsController/ConfigStore.
        assert wizard.action_save_speech() is True
        assert app.composition.provider_controller.config().defaults["speech_setup"] == "deferred"
        assert not wizard._current_form_dirty()
