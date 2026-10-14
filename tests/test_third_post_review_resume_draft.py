"""TPR-02: resuming a saved draft restores that draft's project in a fresh app."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_resume_in_a_fresh_app_loads_the_saved_drafts_project(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(data)))
    async with first.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        first.action_navigate("new")
        await pilot.pause()
        wizard = first.screen
        wizard.query_one("#guided-project-name", Input).value = "Saved project"
        wizard.query_one("#guided-project-topic", Input).value = "Saved topic"
        assert wizard.action_create_project()
        project_id = wizard.context.project_id
        assert wizard.action_continue()
        step = wizard.context.state.current_step
        wizard.action_save_exit()
        await pilot.pause()
        assert wizard.save_exit_requested

    # A completely fresh app instance: no widget state survives, only the draft store.
    second = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(data)))
    async with second.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        second.action_navigate("resume")
        await pilot.pause()
        await pilot.pause()
        resumed = second.screen
        assert resumed.context.project_id == project_id
        assert resumed.context.state.current_step == step

        # Going back shows the saved project's durable values, not blanks.
        assert resumed.action_back()
        await pilot.pause()
        assert resumed.query_one("#guided-project-name", Input).value == "Saved project"
        assert resumed.query_one("#guided-project-topic", Input).value == "Saved topic"
        assert not resumed._current_form_dirty()
