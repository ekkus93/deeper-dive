"""FPR-02 sweep: legacy screen actions report service errors instead of exiting the app."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.screen_guard import report_service_errors
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


class _Screen:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def _status(self, message: str) -> None:
        self.messages.append(message)

    @report_service_errors("Did not work")
    def act(self, error: BaseException | None) -> str:
        if error is not None:
            raise error
        return "ok"


@pytest.mark.parametrize(
    "error", [KeyError("k"), IndexError(), OSError("o"), RuntimeError("r"), ValueError("v")]
)
def test_decorator_reports_recoverable_errors(error: BaseException) -> None:
    screen = _Screen()
    assert screen.act(error) is None
    assert screen.messages and screen.messages[0].startswith("Did not work")


def test_decorator_reports_sqlite_errors_and_passes_results_through() -> None:
    screen = _Screen()
    screen.act(sqlite3.OperationalError("database is locked"))
    assert "locked" in screen.messages[0]
    assert screen.act(None) == "ok"


def test_decorator_does_not_swallow_programming_errors() -> None:
    with pytest.raises(TypeError):
        _Screen().act(TypeError("bug"))


def test_secrets_in_error_text_are_redacted() -> None:
    screen = _Screen()
    screen.act(OSError("failed https://u:CANARYpw@host/x"))
    assert "CANARYpw" not in screen.messages[0]


@pytest.mark.parametrize("error", [OSError("disk full"), sqlite3.OperationalError("locked")])
def test_home_create_project_survives_a_failing_service(tmp_path: Path, error: Exception) -> None:
    async def run() -> None:
        service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
        app = DeeperDiveApp(service)
        async with app.run_test(size=(100, 40)) as pilot:
            screen = app.screen
            screen.query_one("#new-project-name", Input).value = "Doomed"
            with patch.object(DeeperDiveService, "create_project", side_effect=error):
                screen.action_create_project()  # type: ignore[attr-defined]
            await pilot.pause()
            assert app.is_running
            status = str(screen.query_one("#screen-status", Static).render())
            assert "Project not created" in status

    asyncio.run(run())
