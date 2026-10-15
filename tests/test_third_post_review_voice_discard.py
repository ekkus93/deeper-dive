"""TPR-01: discarding after a saved voice vanished must not crash the wizard."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from textual.widgets import Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.settings_screen import SettingsController
from deeper_dive.storage.workspace import WorkspaceManager


def test_discard_after_saved_voice_vanished_keeps_app_alive_and_config_unchanged(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        controller = app.provider_controller
        controller.save_provider("speech", "fake-tts", voices=("voice-a", "voice-b", "voice-c"))
        SettingsController(controller).set_defaults(
            {
                "tts_provider": "speech",
                "tts_voice": "voice-b",
                "tts_voice_host_1": "voice-b",
                "tts_voice_host_2": "voice-c",
                "quick_deep_dive_duration_minutes": "20",
                "research_policy": "useful",
            }
        )
        original = controller.config_store.path.read_bytes()
        wizard._load_existing_setup()
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "voice-defaults")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        wizard._remember_current_form()

        # Normal discovery first: the saved voices are offered and become the
        # clean durable baseline.
        wizard.action_discover_voices()
        await pilot.pause()
        host1 = wizard.query_one("#setup-host1-voice", Select)
        assert host1.value == "voice-b"
        assert not wizard._current_form_dirty()

        provider = controller.tts("speech")
        with patch.object(
            provider,
            "voices",
            return_value=(SimpleNamespace(name="Voice C", id="voice-c"),),
        ):
            wizard.action_discover_voices()
            await pilot.pause()
        assert host1.value is Select.BLANK
        assert wizard._current_form_dirty()

        # Back -> confirmation -> Discard. The durable voice is no longer an
        # option; restoring it must not raise InvalidSelectValueError.
        wizard.action_back()
        await pilot.pause()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_discard_exit()
        await pilot.pause()

        assert app.is_running
        assert controller.config_store.path.read_bytes() == original
        assert host1.value is Select.BLANK
        status = str(wizard.query_one("#wizard-status", Static).render())
        assert "voice" in status.lower()

        # 6PR-10 (FPR-04): a later Save the user did not ask for must not write anything.
        # The voice Select allows blank, so Discard leaves it blank and Save refuses.
        assert wizard.action_save_defaults() is False
        assert "Choose Host 1 and Host 2 voices" in str(
            wizard.query_one("#wizard-status", Static).render()
        )
        assert controller.config_store.path.read_bytes() == original
