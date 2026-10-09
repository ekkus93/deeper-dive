"""Keyboard, compact-layout, and sanitized Help matrix for both guided wizards."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_shell import WizardShell


@pytest.mark.parametrize("size", [(80, 24), (100, 30)])
@pytest.mark.parametrize("destination", ["setup", "new"])
def test_guided_error_details_are_keyboard_accessible_and_redacted(
    tmp_path: Path,
    size: tuple[int, int],
    destination: str,
) -> None:
    asyncio.run(_verify_help_and_focus(tmp_path, size, destination))


async def _verify_help_and_focus(
    tmp_path: Path,
    size: tuple[int, int],
    destination: str,
) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=size) as pilot:
        if destination == "new":
            app.action_navigate("new")
            await pilot.pause()
        screen = app.screen
        assert isinstance(screen, WizardShell)
        expected_ids = {
            "setup": "screen-wizard-first-run",
            "new": "screen-wizard-new-deep-dive",
        }
        assert screen.id == expected_ids[destination]
        assert screen.query_one("#wizard-actions").display
        assert not screen.query_one("#wizard-resize-message").display
        progress = str(screen.query_one("#wizard-progress", Static).render())
        assert len(progress) <= size[0] - 4
        assert "current" in progress
        assert "Step 1 of" in str(screen.query_one("#wizard-heading", Static).render())

        # No secret or raw exception is ever rendered on the normal status line.
        canaries = ("guided-bearer-canary", "guided-api-secret-canary")
        screen.set_error(
            "Synthetic provider failure.",
            RuntimeError(
                "Authorization: Bearer guided-bearer-canary "
                "api_key=guided-api-secret-canary"
            ),
        )
        status = str(screen.query_one("#wizard-status", Static).render())
        assert "Press F1 for details" in status
        assert "Traceback" not in status
        assert all(canary not in status for canary in canaries)

        await pilot.press("f1")
        await pilot.pause()
        details = str(screen.query_one("#wizard-status", Static).render())
        assert "Details:" in details
        assert "[REDACTED]" in details
        assert all(canary not in details for canary in canaries)
        assert "Traceback" not in details

        # Help lives in the stable bottom action row with Tab/Shift+Tab support.
        help_button = screen.query_one("#wizard-help", Button)
        help_button.focus()
        await pilot.press("shift+tab")
        assert screen.focused is screen.query_one("#wizard-save-exit", Button)
        await pilot.press("tab")
        assert screen.focused is help_button

        screen.set_status("Ready")
        assert "Details:" not in str(screen.query_one("#wizard-status", Static).render())
