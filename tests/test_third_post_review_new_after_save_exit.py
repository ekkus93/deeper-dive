"""TPR-02: a fresh New Deep Dive after Save-and-Exit starts clean, not stale or dirty."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_new_deep_dive_after_save_exit_and_abandon_starts_clean(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        wizard.query_one("#guided-project-name", Input).value = "First"
        wizard.query_one("#guided-project-topic", Input).value = "Topic"
        assert wizard.action_create_project()
        await pilot.pause()
        assert wizard.context.project_id is not None
        assert len(service.list_projects()) == 1

        wizard.action_save_exit()
        await pilot.pause()
        assert app.screen is not wizard

        # Start a brand-new deep dive: the saved draft must be abandoned first.
        app.action_navigate("new")
        await pilot.pause()
        app.screen.action_confirm_abandon()
        await pilot.pause()

        old_wizard = wizard
        wizard = app.screen
        assert wizard is not old_wizard
        assert wizard.id == old_wizard.id
        assert wizard.context.project_id is None
        assert wizard.context.state.current_step == "project"
        assert wizard.query_one("#guided-project-name", Input).value == ""
        assert not wizard._current_form_dirty()
        # Clean Back/Continue must be frictionless, not a false unsaved prompt.
        wizard.action_back()
        wizard.action_continue()
        await pilot.pause()
        assert not wizard._exit_confirmation_pending
        assert len(service.list_projects()) == 1
