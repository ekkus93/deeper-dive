"""Home goal-first entry regression."""

import asyncio
from pathlib import Path

from textual.widgets import Button

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_source_wizard import GuidedSourceWizard
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
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


def test_starting_new_flow_requires_confirmed_abandonment_of_saved_draft(tmp_path: Path) -> None:
    asyncio.run(_confirmed_abandonment(tmp_path))


async def _confirmed_abandonment(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Incomplete saved workflow")
    app = GuidedDeeperDiveApp(service)
    drafts = GuidedDraftStore(service.workspaces.data_dir)
    drafts.save(
        WizardContext(
            app.composition,
            WizardState(WizardKind.NEW_DEEP_DIVE, "sources"),
            project_id=project.id,
        )
    )

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        home = app.screen
        assert home.id == "screen-home"
        assert home.query_one("#action-resume-deep-dive", Button).display
        assert home.query_one("#action-abandon-deep-dive", Button).display

        home.query_one("#action-new-deep-dive", Button).press()
        await pilot.pause()
        assert app.screen is home
        assert home.query_one("#action-confirm-abandon-deep-dive", Button).display
        cancel = home.query_one("#action-cancel-abandon-deep-dive", Button)
        assert cancel.display
        assert home.focused is cancel
        assert drafts.has_resume(app.composition)

        cancel.press()
        await pilot.pause()
        assert drafts.has_resume(app.composition)
        assert home.query_one("#action-abandon-deep-dive", Button).display

        home.query_one("#action-new-deep-dive", Button).press()
        await pilot.pause()
        home.query_one("#action-confirm-abandon-deep-dive", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, GuidedSourceWizard)
        assert app.screen.context.state.current_step == "project"
        assert not drafts.has_resume(app.composition)
