"""6PR-05: honest legacy outcomes (partial success) and plan-screen robustness."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from guided_pilot import click, type_into
from test_fourth_post_review_plan_screen_errors import _open_plan, _reach_plan_screen
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewScreen
from deeper_dive.tui import DeeperDiveApp

LOCKED = sqlite3.OperationalError("database is locked")


def _status(screen) -> str:  # type: ignore[no-untyped-def]
    return str(screen.query_one("#screen-status", Static).render())


def test_regenerated_turn_is_not_reported_as_failed_when_only_the_refresh_raises(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
        project = service.create_project("P")
        app = DeeperDiveApp(service)
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            screen = TranscriptReviewScreen()
            await app.push_screen(screen)
            await pilot.pause()
            repaired = MagicMock()
            repaired.id = "t1"
            controller = type(screen.controller)
            # A transcript with a repairable turn needs a full generation run; the
            # behaviour under test is only the status line, so the turn and the repair
            # are stubbed and the refresh read raises like a locked database.
            with (
                patch.object(TranscriptReviewScreen, "_selected_turn", return_value=repaired),
                patch.object(controller, "repair_turn", return_value=None),
                patch.object(controller, "turns", side_effect=LOCKED),
            ):
                screen.action_regenerate_turn()
            assert app.is_running
            status = _status(screen)
            assert "Regenerated selected turn/section" in status
            assert "could not refresh" in status
            assert "Regeneration failed" not in status

    asyncio.run(run())


def _delete_segments(service, project_id: str) -> None:  # type: ignore[no-untyped-def]
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    with database.transaction() as db:
        db.execute("DELETE FROM segment_plans")


def test_reload_plan_with_no_stored_segments_reports_instead_of_crashing(tmp_path: Path) -> None:
    async def run() -> None:
        service, app, project_id = await _open_plan(tmp_path, with_run=False)
        async with app.run_test(size=(100, 40)) as pilot:
            screen = await _reach_plan_screen(app, pilot, service, project_id, with_run=False)
            _delete_segments(service, project_id)
            await click(pilot, "#action-reload-plan")
            assert app.is_running
            assert "no segments" in _status(screen)
            assert screen.query_one("#segment-title", Input).value == ""

    asyncio.run(run())


def test_reload_plan_says_when_it_discarded_unsaved_segment_edits(tmp_path: Path) -> None:
    async def run() -> None:
        service, app, project_id = await _open_plan(tmp_path, with_run=False)
        async with app.run_test(size=(100, 40)) as pilot:
            screen = await _reach_plan_screen(app, pilot, service, project_id, with_run=False)
            stored_title = screen.query_one("#segment-title", Input).value
            await type_into(pilot, "#segment-title", "Unsaved edit")
            await click(pilot, "#action-reload-plan")
            assert "unsaved segment edits were discarded" in _status(screen)
            assert screen.query_one("#segment-title", Input).value == stored_title
            # With nothing edited the plain message is used.
            await click(pilot, "#action-reload-plan")
            assert _status(screen).endswith("Reloaded the stored plan")

    asyncio.run(run())


def test_quick_deep_dive_that_created_the_episode_is_not_reported_as_failed(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
        project = service.create_project("P")
        app = DeeperDiveApp(service)
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            app.action_navigate("episode")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, EpisodeSetupScreen)
            with patch.object(EpisodeSetupScreen, "_planning_assignment", side_effect=LOCKED):
                screen.action_quick_deep_dive()
            assert app.is_running
            status = _status(screen)
            assert "Episode created; planning could not start" in status
            assert "Quick Deep Dive failed" not in status
            assert app.current_episode_id is not None

    asyncio.run(run())


def test_reload_plan_shows_the_stored_plan_after_a_real_conflict(tmp_path: Path) -> None:
    """Replaces the mocked 5PR-07 test: a real stored plan changed by another writer."""

    async def run() -> None:
        service, app, project_id = await _open_plan(tmp_path, with_run=False)
        async with app.run_test(size=(100, 40)) as pilot:
            screen = await _reach_plan_screen(app, pilot, service, project_id, with_run=False)
            controller = app.episode_plan_controller
            episode_id = app.current_episode_id
            assert controller is not None and episode_id is not None
            old_plan = screen.plan
            assert old_plan is not None
            # Another writer (a second window) saves a new version of segment 1.
            changed = replace(old_plan.segments[0], title="Changed elsewhere")
            controller.edit_segment(episode_id, 0, changed)
            stored = controller.load_plan(episode_id)
            assert stored.id != old_plan.id

            await click(pilot, "#action-reload-plan")

            assert screen.plan is not None and screen.plan.id == stored.id
            assert screen.query_one("#segment-title", Input).value == "Changed elsewhere"
            assert _status(screen).endswith("Reloaded the stored plan")
            # Reload never regenerates: the stored plan is exactly what the other writer saved.
            assert controller.load_plan(episode_id) == stored

    asyncio.run(run())
