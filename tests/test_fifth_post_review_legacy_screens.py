"""5PR-07: remaining legacy screen actions survive service errors; honest partial success."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.hosts import HostProfile
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.research_screen import ResearchScreen
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewScreen
from deeper_dive.tui import DeeperDiveApp, HomeProjectsScreen

SRC = Path(__file__).resolve().parent.parent / "src" / "deeper_dive"
LOCKED = sqlite3.OperationalError("database is locked")


def _status(screen) -> str:  # type: ignore[no-untyped-def]
    return str(screen.query_one("#screen-status", Static).render())


async def _open(tmp_path: Path, route: str):  # type: ignore[no-untyped-def]
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("P")
    app = DeeperDiveApp(service)
    return service, project, app


def test_research_actions_report_a_locked_database(tmp_path: Path) -> None:
    async def run() -> None:
        _service, project, app = await _open(tmp_path, "research")
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            app.action_navigate("research")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ResearchScreen)
            controller = MagicMock()
            for name in ("save_policy", "analyze", "research", "set_gap_status", "gaps"):
                getattr(controller, name).side_effect = LOCKED
            with (
                patch.object(ResearchScreen, "_controller", return_value=controller),
                patch.object(ResearchScreen, "_selected_gap", return_value="g1"),
            ):
                for action, label in (
                    (screen.action_save, "Research policy not saved"),
                    (screen.action_analyze, "Analysis failed"),
                    (screen.action_search, "Research failed"),
                    (screen.action_ignore, "Gap not ignored"),
                    (screen.action_research_all, "Research failed"),
                ):
                    action()
                    assert app.is_running
                    assert label in _status(screen), (label, _status(screen))

    asyncio.run(run())


def _fail_writes(service, project_id: str, table: str) -> None:  # type: ignore[no-untyped-def]
    """Make the real repository's writes to ``table`` fail inside SQLite (no mocks)."""

    database = Database(service.workspaces.project_root(project_id) / "project.db")
    with database.transaction() as db:
        for operation in ("INSERT", "UPDATE"):
            db.execute(
                f"CREATE TRIGGER fail_{table}_{operation.lower()} BEFORE {operation} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'disk I/O error'); END"
            )


def test_hosts_save_actions_report_a_real_database_failure(tmp_path: Path) -> None:
    async def run() -> None:
        service, project, app = await _open(tmp_path, "hosts")
        service.hosts(project.id).create_host(HostProfile("h1", project.id, "A").to_record())
        service.hosts(project.id).create_host(HostProfile("h2", project.id, "B").to_record())
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            app.action_navigate("hosts")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, HostsScreen)
            screen.selected_host_id = "h1"
            screen.query_one("#host-name", Input).value = "Renamed"
            screen.query_one("#relationship-target", Input).value = "h2"
            _fail_writes(service, project.id, "hosts")
            _fail_writes(service, project.id, "host_relationships")

            screen.action_save_host()
            assert app.is_running and "Host not saved" in _status(screen)
            screen.action_save_relationship()
            assert app.is_running and "Relationship not saved" in _status(screen)
            # The real repository rejected both writes: nothing was stored.
            assert service.hosts(project.id).get_host("h1").display_name == "A"

    asyncio.run(run())


def test_hosts_save_actions_report_an_os_error(tmp_path: Path) -> None:
    async def run() -> None:
        service, project, app = await _open(tmp_path, "hosts")
        service.hosts(project.id).create_host(HostProfile("h1", project.id, "A").to_record())
        service.hosts(project.id).create_host(HostProfile("h2", project.id, "B").to_record())
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            app.action_navigate("hosts")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, HostsScreen)
            screen.selected_host_id = "h1"
            screen.query_one("#relationship-target", Input).value = "h2"
            repository = type(screen._repository())
            # sqlite never raises OSError on its own here; the patch stands in for a
            # full disk surfacing from the filesystem layer.
            with (
                patch.object(repository, "update_host", side_effect=OSError("disk full")),
                patch.object(repository, "upsert_relationship", side_effect=OSError("disk full")),
            ):
                screen.action_save_host()
                assert app.is_running and "Host not saved" in _status(screen)
                screen.action_save_relationship()
                assert app.is_running and "Relationship not saved" in _status(screen)

    asyncio.run(run())


def test_preflight_generate_reports_a_failing_build(tmp_path: Path) -> None:
    async def run() -> None:
        _service, project, app = await _open(tmp_path, "generate")
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            app.action_navigate("generate")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, PreflightScreen)
            with patch.object(PreflightController, "build", side_effect=LOCKED):
                screen.action_generate()
            assert app.is_running
            assert "Generation blocked" in _status(screen)

    asyncio.run(run())


def test_transcript_export_reports_an_os_error(tmp_path: Path) -> None:
    async def run() -> None:
        _service, project, app = await _open(tmp_path, "transcript")
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            screen = TranscriptReviewScreen()
            await app.push_screen(screen)
            await pilot.pause()
            with patch.object(
                type(screen.controller), "export_markdown", side_effect=OSError("disk full")
            ):
                screen.action_export()
            assert app.is_running
            assert "Export failed" in _status(screen)

    asyncio.run(run())


def test_saved_change_is_not_reported_as_failed_when_only_the_refresh_raises(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        service, _project, app = await _open(tmp_path, "home")
        async with app.run_test(size=(100, 40)) as pilot:
            screen = app.screen
            assert isinstance(screen, HomeProjectsScreen)
            screen.query_one("#new-project-name", Input).value = "Fresh"

            def flaky():  # type: ignore[no-untyped-def]
                raise sqlite3.OperationalError("database is locked")

            with patch.object(DeeperDiveService, "list_project_summaries", side_effect=flaky):
                screen.action_create_project()
            await pilot.pause()
            assert app.is_running
            status = _status(screen)
            assert "Created project: Fresh" in status
            assert "could not refresh" in status
            assert "not created" not in status
            assert any(p.name == "Fresh" for p in service.list_project_summaries())

    asyncio.run(run())
