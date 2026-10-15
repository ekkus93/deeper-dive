"""FPR-10: a picker change under an open prompt cannot replace the pending transition."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import choose_option, click, reach_hosts, type_into
from textual.widgets import Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_transitions import TransitionKind


def test_host_picker_change_under_a_back_prompt_keeps_back(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        await reach_hosts(pilot)
        wizard = app.screen
        await click(pilot, "#guided-host-recommended")
        picker = wizard.query_one("#guided-host-picker", Select)
        first_host = picker.value
        await type_into(pilot, "#guided-host-name", "Edited")
        await click(pilot, "#wizard-back")
        assert wizard._exit_confirmation_pending
        assert wizard._pending_transition is not None
        assert wizard._pending_transition.kind is TransitionKind.BACK

        # The user reaches for the picker while the Back prompt is still open.
        await choose_option(pilot, "#guided-host-picker", 1)

        assert wizard._exit_confirmation_pending
        assert wizard._pending_transition is not None
        assert wizard._pending_transition.kind is TransitionKind.BACK
        assert picker.value == first_host

        await click(pilot, "#wizard-confirm-discard")
        assert wizard.context.state.current_step == "research"


def test_plan_picker_change_under_a_back_prompt_keeps_back(tmp_path: Path) -> None:
    asyncio.run(_plan(tmp_path))


async def _plan(tmp_path: Path) -> None:
    from guided_pilot import reach_plan

    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        await reach_plan(pilot)
        wizard = app.screen
        picker = wizard.query_one("#guided-plan-segment-picker", Select)
        first = picker.value
        await type_into(pilot, "#guided-plan-title", "Unsaved opening title")
        await click(pilot, "#wizard-back")
        assert wizard._exit_confirmation_pending
        assert wizard._pending_transition.kind is TransitionKind.BACK

        await choose_option(pilot, "#guided-plan-segment-picker", 1)

        assert wizard._pending_transition is not None
        assert wizard._pending_transition.kind is TransitionKind.BACK
        assert picker.value == first
