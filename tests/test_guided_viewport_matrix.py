"""Viewport behavior for both production-backed wizard shells."""

import asyncio

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("size", [(100, 30), (80, 24), (79, 24), (80, 23)])
@pytest.mark.parametrize("target", ["setup", "new"])
def test_guided_viewport_matrix(tmp_path, size, target):
    async def run():
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=size) as pilot:
            if target == "new":
                app.action_navigate("new")
                await pilot.pause()
            screen = app.screen
            step = screen.context.state.current_step
            too_small = size[0] < 80 or size[1] < 24
            assert screen.query_one("#wizard-resize-message").display == too_small
            assert screen.query_one("#wizard-content").display != too_small
            assert screen.query_one("#wizard-actions").display != too_small
            assert screen.context.state.current_step == step

    asyncio.run(run())
