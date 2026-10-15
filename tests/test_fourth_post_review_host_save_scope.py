"""FPR-12: Save on a profile-scoped host prompt saves only the profile, like Discard."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import choose_option, click, reach_hosts, type_into
from textual.widgets import Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_transitions import TransitionKind


def test_profile_scoped_save_keeps_the_order_edit_pending(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 45)) as pilot:
        await reach_hosts(pilot)
        wizard = app.screen
        await click(pilot, "#guided-host-recommended")
        await click(pilot, "#guided-host-down")  # unsaved membership/order edit
        reordered = list(wizard._selected_host_ids)
        assert wizard._host_order_dirty()
        picker = wizard.query_one("#guided-host-picker", Select)
        first_host = picker.value
        project_id = wizard.context.project_id

        await type_into(pilot, "#guided-host-name", "Profile Only")
        await choose_option(pilot, "#guided-host-picker", 1)
        assert wizard._pending_transition.kind is TransitionKind.HOST_SELECT
        prompt = str(wizard.query_one("#wizard-status", Static).render())
        assert "Save stores the host profile only" in prompt

        await click(pilot, "#wizard-confirm-save")

        saved = service.hosts(project_id).get_host(first_host)
        assert saved is not None and saved.display_name == "Profile Only"
        # The order edit was not saved and was not silently adopted as clean.
        assert wizard._selected_host_ids == reordered
        assert wizard._host_order_dirty()
