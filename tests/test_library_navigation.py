from __future__ import annotations

import asyncio
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_library_screen import EpisodeLibraryScreen
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def test_library_navigation_uses_episode_library_screen(tmp_path: Path) -> None:
    asyncio.run(_library_navigation(tmp_path))


async def _library_navigation(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Library navigation")
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("library")
        await pilot.pause()
        assert isinstance(app.screen, EpisodeLibraryScreen)
