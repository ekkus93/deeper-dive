"""Voice rediscovery must preserve both dirty defaults and saved voice identity."""

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
from deeper_dive.storage.workspace import WorkspaceManager


def test_voice_rediscovery_guards_dirty_edits_and_preserves_saved_ids(
    tmp_path: Path,
) -> None:
    asyncio.run(_check_voice_discovery(tmp_path))


async def _check_voice_discovery(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    voices = ["alpha", "beta", "gamma"]
    calls: list[tuple[str, ...]] = []

    def available_voices() -> tuple[SimpleNamespace, ...]:
        calls.append(tuple(voices))
        return tuple(SimpleNamespace(id=ident, name=ident.title()) for ident in voices)

    fake = SimpleNamespace(voices=available_voices)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "voice-defaults")
        wizard._sync_text()
        wizard._sync_setup_controls()
        await pilot.pause()
        with (
            patch.object(wizard, "_selected_tts_name", return_value="fixture-speech"),
            patch.object(app.composition.provider_controller, "tts", return_value=fake),
        ):
            wizard.action_discover_voices()
            await pilot.pause()
            first = wizard.query_one("#setup-host1-voice", Select)
            second = wizard.query_one("#setup-host2-voice", Select)
            assert (first.value, second.value) == ("alpha", "beta")
            wizard._remember_current_form()

            first.value = "gamma"
            assert wizard._current_form_dirty()
            wizard.action_discover_voices()
            await pilot.pause()
            assert wizard.query_one("#wizard-exit-confirmation").display
            assert wizard._pending_transition == "discover-voices"
            assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")
            assert calls == [("alpha", "beta", "gamma")]
            assert first.value == "gamma"

            wizard.action_cancel_exit_confirmation()
            assert first.value == "gamma"
            assert wizard._current_form_dirty()
            wizard.action_discover_voices()
            wizard.action_confirm_discard_exit()
            await pilot.pause()
            assert calls == [("alpha", "beta", "gamma")] * 2
            assert (first.value, second.value) == ("alpha", "beta")

            # Provider discovery may reorder IDs; stable voice identity wins.
            wizard._remember_current_form()
            voices[:] = ["beta", "gamma", "alpha"]
            wizard.action_discover_voices()
            await pilot.pause()
            assert (first.value, second.value) == ("alpha", "beta")
            assert not wizard._current_form_dirty()

            # A provider removing a selected voice is actionable, never silent
            # reassignment to an arbitrary new voice.
            voices[:] = ["beta", "gamma"]
            wizard.action_discover_voices()
            await pilot.pause()
            assert first.value == Select.BLANK
            assert second.value == "beta"
            assert "Choose replacement" in str(wizard.query_one("#wizard-status", Static).render())
            assert wizard._current_form_dirty()
