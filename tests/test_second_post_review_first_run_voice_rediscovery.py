"""SPR-01: first-run voice rediscovery cannot silently overwrite saved or dirty choices."""

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


def test_first_run_rediscovery_respects_saved_voices_dirty_cancel_and_provider_errors(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_voice_rediscovery(tmp_path))


async def _exercise_voice_rediscovery(tmp_path: Path) -> None:
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

        wizard.action_discover_voices()
        await pilot.pause()
        host1 = wizard.query_one("#setup-host1-voice", Select)
        host2 = wizard.query_one("#setup-host2-voice", Select)
        assert host1.value == "voice-b"
        assert host2.value == "voice-c"
        assert not wizard._current_form_dirty()

        # Reorder from production without changing the saved voice identities.
        controller.save_provider("speech", "fake-tts", voices=("voice-c", "voice-a", "voice-b"))
        original = controller.config_store.path.read_bytes()
        wizard.action_discover_voices()
        await pilot.pause()
        assert host1.value == "voice-b"
        assert host2.value == "voice-c"
        assert not wizard._current_form_dirty()

        host1.value = "voice-a"
        await pilot.pause()
        assert wizard._current_form_dirty()
        wizard.action_discover_voices()
        await pilot.pause()
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert host1.value == "voice-a"
        wizard.action_cancel_exit_confirmation()
        await pilot.pause()
        assert host1.value == "voice-a"
        assert wizard._current_form_dirty()
        assert controller.config_store.path.read_bytes() == original

        wizard.action_discover_voices()
        wizard.action_confirm_discard_exit()
        await pilot.pause()
        assert host1.value == "voice-b"
        assert host2.value == "voice-c"
        assert controller.config_store.path.read_bytes() == original

        provider = controller.tts("speech")
        with patch.object(provider, "voices", side_effect=RuntimeError("voice-canary")):
            wizard.action_discover_voices()
            await pilot.pause()
        assert host1.value == "voice-b"
        assert "voice-canary" not in str(wizard.query_one("#wizard-status", Static).render())
        assert controller.config_store.path.read_bytes() == original

        # A truly missing saved voice must not silently become another voice.
        with patch.object(
            provider,
            "voices",
            return_value=(SimpleNamespace(name="Voice C", id="voice-c"),),
        ):
            wizard.action_discover_voices()
            await pilot.pause()
        assert host1.value is Select.BLANK
        assert host2.value == "voice-c"
        assert "no longer available" in str(wizard.query_one("#wizard-status", Static).render())
        assert controller.config_store.path.read_bytes() == original
