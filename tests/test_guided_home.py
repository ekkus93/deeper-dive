"""Home goal-first entry regression."""

import asyncio
from pathlib import Path

from textual.widgets import Button

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_source_wizard import GuidedSourceWizard
from deeper_dive.storage.workspace import WorkspaceManager


def test_home_new_deep_dive_action(tmp_path: Path) -> None:
    asyncio.run(_check(tmp_path))


async def _check(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_navigate("home")
        await pilot.pause()
        app.screen.query_one("#action-new-deep-dive", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, GuidedSourceWizard)
        assert app.screen.context.state.current_step == "project"
        first_wizard = app.screen

        app.action_navigate("home")
        await pilot.pause()
        app.screen.query_one("#action-new-deep-dive", Button).press()
        await pilot.pause()
        assert app.screen is first_wizard


def test_returning_project_owner_can_open_home_and_resume_setup(tmp_path: Path) -> None:
    asyncio.run(_returning_project_owner_can_open_home_and_resume_setup(tmp_path))


async def _returning_project_owner_can_open_home_and_resume_setup(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    service.create_project("Existing project")
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        assert app.screen.id == "screen-home"
        await pilot.pause()
        setup = app.screen.query_one("#action-resume-setup", Button)
        assert setup.display
        setup.press()
        await pilot.pause()
        assert app.screen.id == "screen-wizard-first-run"
