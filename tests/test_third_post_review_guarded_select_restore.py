"""TPR-01: guarded Select restore for further voice-rediscovery variants and the host picker."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_third_post_review_host_discard_scope import _run
from textual.pilot import Pilot
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.settings_screen import SettingsController
from deeper_dive.storage.workspace import WorkspaceManager


async def _voices_scenario(tmp_path: Path, rediscovered: object) -> None:
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
        assert host1.value == "voice-b"

        provider = controller.tts("speech")
        if isinstance(rediscovered, Exception):
            patcher = patch.object(provider, "voices", side_effect=rediscovered)
        else:
            patcher = patch.object(provider, "voices", return_value=rediscovered)
        with patcher:
            wizard.action_discover_voices()
            await pilot.pause()

        # Whatever rediscovery did, Back -> Discard must not raise.
        wizard.action_back()
        await pilot.pause()
        if wizard._exit_confirmation_pending:
            wizard.action_confirm_discard_exit()
            await pilot.pause()
        assert app.is_running
        assert controller.config_store.path.read_bytes() == original


def test_discard_after_provider_error_during_rediscovery(tmp_path: Path) -> None:
    asyncio.run(_voices_scenario(tmp_path, RuntimeError("provider unreachable")))


def test_discard_after_voices_were_reordered(tmp_path: Path) -> None:
    reordered = (
        SimpleNamespace(name="Voice C", id="voice-c"),
        SimpleNamespace(name="Voice B", id="voice-b"),
        SimpleNamespace(name="Voice A", id="voice-a"),
    )
    asyncio.run(_voices_scenario(tmp_path, reordered))


async def _host_picker_original_vanished(
    wizard: GuidedEpisodeWizard, pilot: Pilot, service: DeeperDiveService, project_id: str
) -> None:
    wizard.query_one("#guided-host-instructions", Input).value = "Unsaved profile edit"
    picker = wizard.query_one("#guided-host-picker", Select)
    original = wizard._loaded_host_id
    assert original == "first"
    # The edited host disappears from the offered options (e.g. deleted elsewhere).
    picker.set_options([("Second", "second")])
    await pilot.pause()
    picker.value = "second"  # must not raise InvalidSelectValueError restoring "first"
    await pilot.pause()
    assert wizard.is_attached


def test_host_picker_restore_survives_a_vanished_original(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path, _host_picker_original_vanished, with_episode=True))
