from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, ListView

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def _app(tmp_path: Path) -> tuple[DeeperDiveApp, DeeperDiveService]:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    return DeeperDiveApp(service), service


def test_home_create_open_rename_delete_and_cancel(tmp_path: Path) -> None:
    asyncio.run(_home_workflow(tmp_path))


async def _home_workflow(tmp_path: Path) -> None:
    app, service = _app(tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.click("#new-project")
        app.screen.query_one("#project-name", Input).value = "Alpha"
        await pilot.click("#save")
        await pilot.pause()
        projects = service.list_projects()
        assert [project.name for project in projects] == ["Alpha"]

        project_list = app.screen.query_one("#project-list", ListView)
        project_list.index = 0
        await pilot.click("#rename-project")
        app.screen.query_one("#project-name", Input).value = "Renamed"
        await pilot.click("#save")
        await pilot.pause()
        assert service.list_projects()[0].name == "Renamed"

        app.screen.query_one("#project-list", ListView).index = 0
        await pilot.click("#delete-project")
        await pilot.click("#cancel-delete")
        await pilot.pause()
        assert len(service.list_projects()) == 1

        app.screen.query_one("#project-list", ListView).index = 0
        await pilot.click("#open-project")
        await pilot.pause()
        assert app.screen.id == "screen-sources"
        assert app.current_project_id == projects[0].id

        await pilot.press("h")
        await pilot.pause()
        app.screen.query_one("#project-list", ListView).index = 0
        await pilot.click("#delete-project")
        await pilot.click("#confirm-delete")
        await pilot.pause()
        assert service.list_projects() == []


def test_home_surfaces_paused_run_status_placeholder(tmp_path: Path) -> None:
    app, service = _app(tmp_path)
    project = service.create_project("Status project")
    summaries = service.list_project_summaries()
    assert summaries[0].project.id == project.id
    assert summaries[0].run_status == "Ready"
    asyncio.run(_assert_status_visible(app))


async def _assert_status_visible(app: DeeperDiveApp) -> None:
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        item = app.screen.query_one("#project-list", ListView).children[0]
        assert "status Ready" in str(item.render())
