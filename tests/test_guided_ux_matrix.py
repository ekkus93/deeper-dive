"""Deterministic keyboard, viewport, and non-color progress regression matrix."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("width,height", ((100, 30), (80, 24), (79, 23)))
def test_first_run_viewport_progress_and_recoverability(
    tmp_path: Path, width: int, height: int
) -> None:
    asyncio.run(_first_run_viewport_progress(tmp_path, width, height))


async def _first_run_viewport_progress(tmp_path: Path, width: int, height: int) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.id == "screen-wizard-first-run"
        heading = str(screen.query_one("#wizard-heading").render())
        progress = str(screen.query_one("#wizard-progress", Static).render())
        assert "Step 1 of 8" in heading
        assert "Welcome (current)" in progress
        assert "Configure Provider (upcoming)" in progress

        too_small = width < 80 or height < 24
        warning = screen.query_one("#wizard-resize-message", Static)
        actions = screen.query_one("#wizard-actions")
        content = screen.query_one("#wizard-content")
        assert warning.display is too_small
        assert actions.display is not too_small
        assert content.display is not too_small
        if too_small:
            assert "80x24" in str(warning.render())
            assert screen.context.state.current_step == "welcome"
        else:
            save_exit = screen.query_one("#wizard-save-exit", Button)
            assert save_exit.display
            screen.action_help()
            assert "Tab/Shift+Tab" in str(screen.query_one("#wizard-status", Static).render())
            await pilot.press("tab")
            assert screen.focused is not None
            assert screen.context.state.current_step == "welcome"
