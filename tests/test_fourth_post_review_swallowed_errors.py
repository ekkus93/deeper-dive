"""FPR-13: errors are shown (not swallowed or fatal) and nothing is silently emptied."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

from guided_pilot import click, reach_hosts, reach_plan
from test_third_post_review_setup_screen_errors import _open_screen
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def _status(wizard) -> str:  # type: ignore[no-untyped-def]
    return str(wizard.query_one("#wizard-status", Static).render())


def test_existing_plan_is_shown_even_when_model_roles_are_unusable(tmp_path: Path) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await reach_plan(pilot)
            wizard = app.screen
            assert wizard._plan is not None
            # Reading a plan needs no model: remove the planning assignment entirely.
            app.provider_controller.save_provider(
                "fake", "fake", default_model="fake-v1", default_updates={"episode_planning": ""}
            )
            wizard._plan = None
            wizard._refresh_plan()
            assert wizard._plan is not None, "an existing plan must not depend on model roles"

    asyncio.run(run())


def test_plan_load_failure_is_reported_not_silent(tmp_path: Path) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await reach_plan(pilot)
            wizard = app.screen
            with patch.object(EpisodePlannerService, "load_plan", side_effect=OSError("disk gone")):
                wizard._refresh_plan()
            assert wizard._plan is None
            assert "could not be loaded" in _status(wizard).lower()

    asyncio.run(run())


def test_setup_screen_survives_a_locked_database_while_planning(tmp_path: Path) -> None:
    async def run() -> None:
        service, app, project_id = await _open_screen(tmp_path)
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project_id
            app.action_navigate("episode")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, EpisodeSetupScreen)
            screen.query_one("#episode-title", Input).value = "T"
            screen.query_one("#episode-hosts", Input).value = "h2, h1"
            error = sqlite3.OperationalError("database is locked")
            with patch.object(EpisodePlannerService, "build_plan", side_effect=error):
                await click(pilot, "#action-build-plan")
            assert app.is_running
            status = str(screen.query_one("#screen-status", Static).render())
            assert "Planning failed" in status

    asyncio.run(run())


def test_host_order_survives_a_resume_without_an_episode(tmp_path: Path) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await reach_hosts(pilot)
            wizard = app.screen
            await click(pilot, "#guided-host-recommended")
            before = list(wizard._selected_host_ids)
            assert len(before) == 2 and wizard.context.episode_id is None
            wizard.on_screen_resume()
            assert wizard._selected_host_ids == before

    asyncio.run(run())


def test_host_order_survives_a_failing_load_on_resume(tmp_path: Path) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await reach_plan(pilot)
            wizard = app.screen
            before = list(wizard._selected_host_ids)
            assert len(before) == 2
            real = EpisodeConfigurationService.load_configuration

            def failing_for_host_order(self, episode_id):  # type: ignore[no-untyped-def]
                # Only the host-order loader fails; readiness probes keep working.
                if sys._getframe(1).f_code.co_name == "_load_episode_host_order":
                    raise OSError("io")
                return real(self, episode_id)

            with patch.object(
                EpisodeConfigurationService, "load_configuration", failing_for_host_order
            ):
                wizard.on_screen_resume()
            assert wizard._selected_host_ids == before
            assert "host order" in _status(wizard).lower()

    asyncio.run(run())
