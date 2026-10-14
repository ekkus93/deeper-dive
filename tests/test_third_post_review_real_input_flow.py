"""TPR-18: a New Deep Dive reaches the hosts step using only real clicks and key presses."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import add_pasted_source, click, continue_step, create_project, type_into
from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_new_deep_dive_reaches_hosts_with_real_input_and_discard_is_scoped(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 40)) as pilot:
        app._first_run_readiness.close()
        await pilot.pause()
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        project_id = await create_project(pilot, "Real input", "Does typing work")
        await continue_step(pilot, "sources")
        await add_pasted_source(pilot, "Notes", "Evidence for the real input flow.")
        await continue_step(pilot, "research")
        await click(pilot, "#guided-research-save")
        await continue_step(pilot, "hosts")

        # Edit a host-profile field by typing, then leave with a real Back click.
        await click(pilot, "#guided-host-recommended")
        instructions = wizard.query_one("#guided-host-instructions", Input)
        original = instructions.value
        await type_into(pilot, "#guided-host-instructions", "typed by a user")
        assert wizard._current_form_dirty()
        await click(pilot, "#wizard-back")
        assert wizard._exit_confirmation_pending
        await click(pilot, "#wizard-confirm-discard")
        assert wizard.context.state.current_step == "research"
        assert service.open_project(project_id) is not None
        assert instructions.value == original
