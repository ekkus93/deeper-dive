from __future__ import annotations

import asyncio
from pathlib import Path

from deeper_dive.tui import GLOBAL_SCREENS, PROJECT_SCREENS, DeeperDiveApp


def test_shell_navigates_all_destinations(tmp_path: Path) -> None:
    asyncio.run(_navigate_all_destinations(tmp_path))


async def _navigate_all_destinations(tmp_path: Path) -> None:
    app = DeeperDiveApp(data_dir=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        assert app.screen.id == "screen-home"
        for destination in (*GLOBAL_SCREENS[1:], *PROJECT_SCREENS):
            await pilot.press(*_shortcut(destination))
            await pilot.pause()
            assert app.screen.id == f"screen-{destination}"
            assert app.screen.query_one("#screen-status") is not None


def test_shell_runs_at_minimum_terminal_size(tmp_path: Path) -> None:
    asyncio.run(_run_at_minimum_terminal_size(tmp_path))


async def _run_at_minimum_terminal_size(tmp_path: Path) -> None:
    app = DeeperDiveApp(data_dir=tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("1")
        await pilot.pause()
        assert app.screen.id == "screen-sources"
        await pilot.press("h")
        await pilot.pause()
        assert app.screen.id == "screen-home"


def test_projects_create_open_rename_delete_and_cancel(tmp_path: Path) -> None:
    asyncio.run(_project_workflow(tmp_path))


async def _project_workflow(tmp_path: Path) -> None:
    app = DeeperDiveApp(data_dir=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.click("#project-new")
        await pilot.click("#project-name")
        await pilot.press(*"Alpha")
        await pilot.click("#dialog-save")
        await pilot.pause()
        project = app.service.list_projects()[0]
        assert project.name == "Alpha"

        await pilot.click("#project-rename")
        name = app.screen.query_one("#project-name")
        name.value = "Renamed"
        await pilot.click("#dialog-save")
        await pilot.pause()
        assert app.service.open_project(project.id).name == "Renamed"  # type: ignore[union-attr]

        await pilot.click("#project-delete")
        await pilot.click("#delete-cancel")
        await pilot.pause()
        assert app.service.open_project(project.id) is not None

        await pilot.click("#project-open")
        await pilot.pause()
        assert app.current_project_id == project.id
        assert app.screen.id == "screen-sources"
        await pilot.press("h")
        await pilot.pause()

        await pilot.click("#project-delete")
        await pilot.click("#delete-confirm")
        await pilot.pause()
        assert app.service.list_projects() == []


def _shortcut(destination: str) -> tuple[str, ...]:
    return {
        "providers": ("p",),
        "settings": ("s",),
        "help": ("?",),
        "sources": ("1",),
        "research": ("2",),
        "hosts": ("3",),
        "episode": ("4",),
        "generate": ("5",),
        "library": ("6",),
    }[destination]
