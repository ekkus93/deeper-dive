"""TPR-18: host reselect and discard driven only by real clicks, typing and keys."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import choose_option, click, reach_hosts, type_into
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_transitions import TransitionKind


def test_typed_host_edit_blocks_reselect_until_discarded(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 45)) as pilot:
        await reach_hosts(pilot)
        wizard = app.screen
        await click(pilot, "#guided-host-recommended")
        picker = wizard.query_one("#guided-host-picker", Select)
        first_host = picker.value
        assert isinstance(first_host, str)
        name = wizard.query_one("#guided-host-name", Input)
        durable_name = name.value

        await type_into(pilot, "#guided-host-name", "Typed Name")
        assert wizard._current_form_dirty()

        await choose_option(pilot, "#guided-host-picker", 1)
        # The reselect is held behind a prompt; the edit and the target survive.
        assert wizard._exit_confirmation_pending
        assert wizard._pending_transition is not None
        assert wizard._pending_transition.kind is TransitionKind.HOST_SELECT
        assert picker.value == first_host
        assert name.value == "Typed Name"

        await click(pilot, "#wizard-confirm-discard")
        assert not wizard._exit_confirmation_pending
        assert picker.value != first_host
        assert name.value != "Typed Name"
        # The first host's stored profile was never touched by the discarded edit.
        project_id = wizard.context.project_id
        assert project_id is not None
        stored = app.service.hosts(project_id).get_host(first_host)
        assert stored is not None
        assert stored.display_name == durable_name


def test_typed_host_edit_saved_from_reselect_prompt_persists(tmp_path: Path) -> None:
    asyncio.run(_save_path(tmp_path))


async def _save_path(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 45)) as pilot:
        await reach_hosts(pilot)
        wizard = app.screen
        await click(pilot, "#guided-host-recommended")
        picker = wizard.query_one("#guided-host-picker", Select)
        first_host = picker.value
        assert isinstance(first_host, str)

        await type_into(pilot, "#guided-host-name", "Saved Via Prompt")
        await choose_option(pilot, "#guided-host-picker", 1)
        assert wizard._exit_confirmation_pending
        await click(pilot, "#wizard-confirm-save")

        assert not wizard._exit_confirmation_pending
        assert picker.value != first_host
        project_id = wizard.context.project_id
        assert project_id is not None
        record = service.hosts(project_id).get_host(first_host)
        assert record is not None
        assert record.display_name == "Saved Via Prompt"
