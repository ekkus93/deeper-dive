"""Keyboard, focus, non-color status, and compact viewport acceptance matrix.

Exercise the real first-run and New Deep Dive screens, not only the shared
WizardShell harness, at both supported terminal dimensions.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("workflow", ["first-run", "new-deep-dive"])
@pytest.mark.parametrize("size", [(80, 24), (100, 30)])
def test_real_guided_wizard_accessibility_focus_and_layout_matrix(
    tmp_path: Path, workflow: str, size: tuple[int, int]
) -> None:
    asyncio.run(_exercise_accessibility_matrix(tmp_path, workflow, size))


async def _exercise_accessibility_matrix(
    tmp_path: Path, workflow: str, size: tuple[int, int]
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=size) as pilot:
        if workflow == "new-deep-dive":
            app.action_navigate("new")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, GuidedEpisodeWizard)
            first = screen.query_one("#guided-project-name", Input)
            second = screen.query_one("#guided-project-topic", Input)
            first.value = "Preserve this draft"
            expected_value = first.value
        else:
            screen = app.screen
            assert isinstance(screen, GuidedFirstRunWizard)
            first = screen.query_one("#setup-mode", Select)
            second = screen.query_one("#setup-skip", Button)
            expected_value = first.value

        heading = str(screen.query_one("#wizard-heading", Static).render())
        progress = str(screen.query_one("#wizard-progress", Static).render())
        assert "Step 1 of" in heading
        assert "(current)" in progress
        assert "▶" in progress  # Completion state is conveyed without color.
        assert screen.query_one("#wizard-content").display
        assert not screen.query_one("#wizard-resize-message", Static).display

        for action in ("back", "continue", "save-exit", "help"):
            button = screen.query_one(f"#wizard-{action}", Button)
            assert button.region.width > 0
            assert button.region.right <= size[0]
            assert button.region.bottom <= size[1]

        # Real workflow controls must be reachable in visual reading order,
        # and Shift+Tab must reverse the same keyboard-only transition.
        first.focus()
        await pilot.press("tab")
        assert screen.focused is second
        await pilot.press("shift+tab")
        assert screen.focused is first

        # A shared action can be activated with Space without a mouse.
        screen.query_one("#wizard-help", Button).focus()
        await pilot.press("space")
        await pilot.pause()
        assert screen.help_requested
        assert "Help:" in str(screen.query_one("#wizard-status", Static).render())

        # Test both independent minimum dimensions and restoration, retaining
        # the in-progress step and any unsaved visible form selection/text.
        current_step = screen.context.state.current_step
        for width, height in ((79, 24), (80, 23)):
            screen._apply_viewport_policy(width, height)
            assert screen.query_one("#wizard-resize-message", Static).display
            assert not screen.query_one("#wizard-actions").display
            assert not screen.query_one("#wizard-content").display
            assert screen.context.state.current_step == current_step
            assert first.value == expected_value
            screen._apply_viewport_policy(*size)
            assert screen.query_one("#wizard-actions").display
            assert screen.query_one("#wizard-content").display
            assert not screen.query_one("#wizard-resize-message", Static).display
            assert screen.context.state.current_step == current_step
            assert first.value == expected_value
