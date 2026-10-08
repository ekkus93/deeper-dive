"""Guided New Deep Dive project acceptance through the real workspace service."""

import asyncio
from pathlib import Path

from textual.widgets import Button, Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_new_deep_dive import GuidedProjectWizard
from deeper_dive.storage.workspace import WorkspaceManager


def test_guided_project_creation_is_durable(tmp_path: Path) -> None:
    asyncio.run(_guided_project_creation_is_durable(tmp_path))


async def _guided_project_creation_is_durable(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedProjectWizard)
        screen.query_one("#guided-project-name", Input).value = "Climate"
        screen.query_one("#guided-project-topic", Input).value = "How do oceans store heat?"
        screen.query_one("#guided-project-create", Button).press()
        await pilot.pause()
        project_id = screen.context.project_id
        assert project_id is not None
        project = service.open_project(project_id)
        assert project is not None
        assert project.name == "Climate"
        assert project.instructions == "How do oceans store heat?"
        assert not screen.query_one("#wizard-continue", Button).disabled
        screen.action_continue()
        assert screen.context.state.current_step == "sources"

    assert service.open_project(project_id) is not None
