"""TPR-11: project-step edits made after the project exists are saved, not looped."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_edit_after_creation_saves_through_the_project_service(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        wizard.query_one("#guided-project-name", Input).value = "Oceans"
        wizard.query_one("#guided-project-topic", Input).value = "Why tides"
        assert wizard.action_create_project()
        project_id = wizard.context.project_id
        assert project_id is not None

        assert wizard.action_continue()
        assert wizard.context.state.current_step != "project"
        assert wizard.action_back()
        assert wizard.context.state.current_step == "project"

        wizard.query_one("#guided-project-topic", Input).value = "Why moons"
        wizard.query_one("#guided-project-name", Input).value = "Oceans 2"
        wizard.action_continue()
        await pilot.pause()
        assert wizard._exit_confirmation_pending

        wizard.action_confirm_save_exit()
        await pilot.pause()

        assert not wizard._exit_confirmation_pending
        assert wizard.context.state.current_step != "project"
        projects = service.list_projects()
        assert len(projects) == 1
        assert projects[0].id == project_id
        assert projects[0].name == "Oceans 2"
        assert "Main curiosity: Why moons" in projects[0].instructions
