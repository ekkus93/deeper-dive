from __future__ import annotations

import asyncio
from pathlib import Path

from textual.containers import VerticalScroll
from textual.widgets import Button

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def _app(tmp_path: Path) -> DeeperDiveApp:
    return DeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))


def test_primary_screens_are_scrollable_at_80x24(tmp_path: Path) -> None:
    asyncio.run(_minimum_terminal(tmp_path))


async def _minimum_terminal(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        for key in ("h", "p", "s", "?", "1", "2", "3", "4", "5", "6"):
            await pilot.press(key)
            await pilot.pause()
            content = app.screen.query_one("#content", VerticalScroll)
            assert content.region.width > 0
            assert content.region.height > 0
            assert app.screen.query_one("#screen-status") is not None


def test_large_terminal_preserves_navigation_and_content_width(tmp_path: Path) -> None:
    asyncio.run(_large_terminal(tmp_path))


async def _large_terminal(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.press("1")
        await pilot.pause()
        content = app.screen.query_one("#content", VerticalScroll)
        assert content.region.width >= 150
        for action in ("#action-add-paste", "#action-add-files", "#action-add-urls"):
            button = app.screen.query_one(action, Button)
            assert button.region.width > 0
            assert button.region.x < 160
