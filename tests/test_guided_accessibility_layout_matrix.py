"""Keyboard-visible action and viewport policy matrix for both guided wizards."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("size", [(100, 30), (80, 24)])
def test_both_wizards_keep_actions_and_non_color_progress_visible(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    asyncio.run(_check_supported_viewports(tmp_path, size))


async def _check_supported_viewports(tmp_path: Path, size: tuple[int, int]) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        for destination, label in ((None, "Welcome"), ("new", "Project Setup")):
            if destination is not None:
                app.action_navigate(destination)
                await pilot.pause()
            screen = app.screen
            assert screen.query_one("#wizard-content", VerticalScroll).display
            actions = screen.query_one("#wizard-actions", Horizontal)
            assert actions.display
            assert actions.region.width <= size[0]
            assert actions.region.x >= 0
            assert actions.region.y + actions.region.height <= size[1]
            assert not screen.query_one("#wizard-resize-message", Static).display
            progress = str(screen.query_one("#wizard-progress", Static).render())
            assert f"▶ {label} (current)" in progress
            assert "○" in progress
            assert screen.query_one("#wizard-back", Button).disabled
            for action in ("continue", "save-exit", "help"):
                assert screen.query_one(f"#wizard-{action}", Button).display
            screen.query_one("#wizard-help", Button).press()
            await pilot.pause()
            assert "Help:" in str(screen.query_one("#wizard-status", Static).render())


@pytest.mark.parametrize("size", [(79, 23), (80, 23), (79, 24)])
def test_below_minimum_viewport_preserves_both_wizard_steps(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    asyncio.run(_check_below_minimum_viewports(tmp_path, size))


async def _check_below_minimum_viewports(tmp_path: Path, size: tuple[int, int]) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        for destination in (None, "new"):
            if destination is not None:
                app.action_navigate(destination)
                await pilot.pause()
            screen = app.screen
            original_step = screen.context.state.current_step
            warning = screen.query_one("#wizard-resize-message", Static)
            assert warning.display
            assert "Resize to at least 80x24" in str(warning.render())
            assert "workflow state is preserved" in str(warning.render())
            assert not screen.query_one("#wizard-content", VerticalScroll).display
            assert not screen.query_one("#wizard-actions", Horizontal).display
            assert screen.context.state.current_step == original_step
