"""5PR-07: remaining legacy screen actions survive service errors; honest partial success."""

from __future__ import annotations

import ast
import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from guided_pilot import click
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_plan_screen import EpisodePlanScreen
from deeper_dive.hosts import HostProfile
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.research_screen import ResearchScreen
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


def test_hosts_save_actions_report_a_locked_database(tmp_path: Path) -> None:
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
            repository = type(screen._repository())
            with (
                patch.object(repository, "update_host", side_effect=LOCKED),
                patch.object(repository, "upsert_relationship", side_effect=LOCKED),
            ):
                screen.action_save_host()
                assert app.is_running and "Host not saved" in _status(screen)
                screen.action_save_relationship()
                assert app.is_running and "Relationship not saved" in _status(screen)
            assert service.hosts(project.id).get_host("h1").display_name == "A"

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
            real = service.list_project_summaries
            calls = {"n": 0}

            def flaky():  # type: ignore[no-untyped-def]
                calls["n"] += 1
                raise sqlite3.OperationalError("database is locked")

            with patch.object(DeeperDiveService, "list_project_summaries", side_effect=flaky):
                screen.action_create_project()
            _ = real
            await pilot.pause()
            assert app.is_running
            status = _status(screen)
            assert "Created project: Fresh" in status
            assert "could not refresh" in status
            assert "not created" not in status
            assert any(p.name == "Fresh" for p in service.list_project_summaries())

    asyncio.run(run())


def test_plan_screen_reload_shows_the_stored_plan_after_a_conflict(tmp_path: Path) -> None:
    async def run() -> None:
        _service, _project, app = await _open(tmp_path, "plan")
        async with app.run_test(size=(100, 40)) as pilot:
            app.action_navigate("plan")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, EpisodePlanScreen)
            old = MagicMock()
            old.segments = []
            newer = MagicMock()
            newer.segments = []
            controller = MagicMock()
            controller.load_plan.return_value = newer
            app.current_episode_id = "e1"
            app.episode_plan_controller = controller
            screen.plan = old
            with (
                patch.object(EpisodePlanScreen, "_render_plan"),
                patch.object(EpisodePlanScreen, "_load_selected"),
            ):
                await click(pilot, "#action-reload-plan")
            assert screen.plan is newer
            assert "Reloaded" in _status(screen)
            controller.regenerate_plan.assert_not_called()

    asyncio.run(run())


_SCREEN_FILES = {
    "episode_plan_screen.py",
    "episode_setup_screen.py",
    "generation_monitor.py",
    "hosts_screen.py",
    "preflight_screen.py",
    "providers_screen.py",
    "research_screen.py",
    "settings_screen.py",
    "transcript_review_screen.py",
    "tui.py",
    "claim_inspector_screen.py",
}

# Actions that call no service, or that already catch what their service can raise
# (the reason is the dictionary value). Anything else must carry
# ``@report_service_errors``.
_REVIEWED = {
    "EpisodePlanScreen": "own _SERVICE_ERRORS handling (FPR-02)",
    "EpisodeSetupScreen": "5PR-10",
    "GenerationMonitorScreen": "except Exception with user_status",
    "ProvidersScreen": "catch KeyError/ValueError/RuntimeError/OSError; config is JSON, not sqlite",
    "SettingsScreen": "_save catches OSError/TypeError/ValueError; config is JSON, not sqlite",
}


def test_every_legacy_service_action_is_guarded_or_reviewed() -> None:
    unguarded: list[str] = []
    for name in sorted(_SCREEN_FILES):
        tree = ast.parse((SRC / name).read_text())
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            if cls.name in _REVIEWED:
                continue
            for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef)):
                if not fn.name.startswith("action_"):
                    continue
                source = ast.unparse(fn)
                touches_service = any(
                    marker in source
                    for marker in ("service", "controller", "repository", "_controller(")
                )
                guarded = any("report_service_errors" in ast.unparse(d) for d in fn.decorator_list)
                if touches_service and not guarded:
                    unguarded.append(f"{name}:{cls.name}.{fn.name}")
    assert unguarded == [], unguarded


@pytest.mark.parametrize("status", ["Ready", "Saved host"])
def test_tolerate_refresh_errors_keeps_the_success_text(status: str) -> None:
    from deeper_dive.screen_guard import tolerate_refresh_errors

    class Screen:
        messages: list[str]

        def __init__(self) -> None:
            self.messages = []

        def _status(self, message: str) -> None:
            self.messages.append(message)

        @tolerate_refresh_errors
        def refresh(self, status: str = "Ready") -> None:
            raise OSError("https://u:CANARY9x@host/x")

    screen = Screen()
    screen.refresh(status)
    assert screen.messages[0].startswith(status)
    assert "could not refresh" in screen.messages[0]
    assert "CANARY9x" not in screen.messages[0]
