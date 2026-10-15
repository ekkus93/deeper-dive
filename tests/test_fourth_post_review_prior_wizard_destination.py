"""FPR-11: the original destination runs exactly once after the dirty-prior prompt."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_workflow import WizardKind
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("destination", ["new", "resume"])
@pytest.mark.parametrize("resolution", ["save", "discard"])
def test_destination_runs_once_after_the_prompt(
    tmp_path: Path, destination: str, resolution: str
) -> None:
    asyncio.run(_exercise(tmp_path, destination, resolution))


async def _exercise(tmp_path: Path, destination: str, resolution: str) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app._first_run_readiness.close()
        app.action_navigate("new")
        await pilot.pause()
        first = app.screen
        first.query_one("#guided-project-name", Input).value = "Oceans"
        first.query_one("#guided-project-topic", Input).value = "Tides"
        assert first.action_create_project()
        # A checkpoint at the project step exists for Resume ...
        GuidedDraftStore(service.workspaces.data_dir).save(first.context)
        app.action_navigate("resume")
        await pilot.pause()
        await pilot.pause()
        wizard = app.screen
        # ... but the open wizard has since moved on and holds an unsaved edit.
        assert wizard.action_continue()
        await pilot.pause()
        assert wizard.context.state.current_step == "sources"
        wizard.query_one("#guided-source-title", Input).value = "Unsaved source title"
        wizard.query_one("#guided-source-text", Input).value = "Unsaved source body"
        assert wizard._current_form_dirty()

        app.push_screen("home")  # something else buries the dirty wizard
        await pilot.pause()
        app.action_navigate(destination)
        await pilot.pause()
        await pilot.pause()
        assert app.screen is wizard and wizard._exit_confirmation_pending

        if resolution == "save":
            wizard.action_confirm_save_exit()
        else:
            wizard.action_confirm_discard_exit()
        await pilot.pause()
        await pilot.pause()

        landed = app.screen
        assert landed is not app.get_screen("home")
        if destination == "new":
            assert landed.context.project_id is None
        else:
            # Resume ran: the checkpointed step, not the step the old wizard was on.
            assert landed.context.state.kind is WizardKind.NEW_DEEP_DIVE
            assert landed.context.state.current_step == "project"
