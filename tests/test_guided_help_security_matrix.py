"""Keyboard, compact-layout, and sanitized Help matrix for both guided wizards."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

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
        sensitive = "Bearer guided-bearer-canary"
        sensitive += " api_key=guided-api-secret-canary"
        screen.set_error(
            "Synthetic provider failure.",
            RuntimeError(f"Authorization: {sensitive}"),
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


def test_guided_host_failure_details_are_help_only(tmp_path: Path) -> None:
    asyncio.run(_verify_host_error_help(tmp_path))


async def _verify_host_error_help(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Synthetic host repair")
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        screen.context.project_id = project.id
        with patch.object(
            service,
            "hosts",
            side_effect=RuntimeError("api_key=host-private-canary"),
        ):
            screen.action_create_host()
        status = str(screen.query_one("#wizard-status", Static).render())
        assert "Host creation failed. Press F1 for details." in status
        assert "host-private-canary" not in status
        screen.action_help()
        details = str(screen.query_one("#wizard-status", Static).render())
        assert "Details:" in details
        assert "[REDACTED]" in details
        assert "host-private-canary" not in details
        assert not service.hosts(project.id).list_hosts(project.id)
