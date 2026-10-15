"""5PR-10: residuals of FPR-07/13/14 and latent defects in Discard, Create Host and the picker."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import patch

from guided_pilot import choose_option, click, reach_hosts
from test_episode_planner import _service
from textual.widgets import Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp

LOCKED = sqlite3.OperationalError("database is locked")


def test_setup_screen_database_errors_keep_the_app_alive(tmp_path: Path) -> None:
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
            with patch.object(HostEpisodeRepository, "list_hosts", side_effect=LOCKED):
                screen.action_build_plan()
                assert "Episode not planned" in str(screen.query_one("#screen-status").render())
                screen.refresh_summary()
                assert "Host summary unavailable" in str(
                    screen.query_one("#screen-status").render()
                )
            with patch.object(DeeperDiveService, "quick_deep_dive", side_effect=LOCKED):
                screen.action_quick_deep_dive()
            assert app.is_running
            assert "Quick Deep Dive failed" in str(screen.query_one("#screen-status").render())

    asyncio.run(run())


def test_a_stale_host_order_notice_does_not_survive_a_later_load(tmp_path: Path) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 40)) as pilot:
            app._first_run_readiness.close()
            app.action_navigate("new")
            await pilot.pause()
            wizard = app.screen
            assert isinstance(wizard, GuidedEpisodeWizard) or hasattr(wizard, "host_order_notice")
            # Seeded: a failed load needs a broken database; the point is the later load.
            wizard.host_order_notice = "Could not load the saved episode host order: old failure"
            wizard.context.episode_id = None
            assert wizard._load_episode_host_order() is False
            assert wizard.host_order_notice == ""

    asyncio.run(run())


def test_load_plan_reads_once(tmp_path: Path) -> None:
    service, episode_id, _ = _service(tmp_path)
    plan = service.build_plan(episode_id)
    opened = 0
    real = Database.connection

    def counting(self):  # type: ignore[no-untyped-def]
        nonlocal opened
        opened += 1
        return real(self)

    with patch.object(Database, "connection", counting):
        assert service.load_plan(episode_id) == plan
    assert opened == 1


def test_discard_with_an_unavailable_value_on_a_non_blank_select_does_not_raise(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)):
            app._first_run_readiness.close()
            wizard = app.screen
            assert isinstance(wizard, GuidedFirstRunWizard)
            # Seeded: the durable choice vanishing from an allow_blank=False Select is a
            # race (config edited elsewhere) that no UI path holds still.
            wizard.context.state = WizardState(WizardKind.FIRST_RUN, "voice-defaults")
            wizard._form_baselines["voice-defaults"] = (("setup-duration", "99"),)
            wizard._restore_discarded_form()
            duration = wizard.query_one("#setup-duration", Select)
            assert duration.value in {"10", "20", "30"}
            assert "setup-duration" in wizard._discard_unavailable

    asyncio.run(run())


def test_create_host_double_submit_window_ends_when_another_host_is_loaded(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await reach_hosts(pilot)
            wizard = app.screen
            project_id = wizard.context.project_id
            assert project_id is not None
            repo = app.composition.service.hosts(project_id)

            def count() -> int:
                return len(repo.list_hosts(project_id))

            await click(pilot, "#guided-host-recommended")
            base = count()
            await click(pilot, "#guided-host-create")
            assert count() == base + 1
            await click(pilot, "#guided-host-create")  # double submit: still blocked
            assert count() == base + 1
            created = wizard._loaded_host_id
            # Select a different host with real keys, then come back to the created one.
            await choose_option(pilot, "#guided-host-picker", steps_down=1)
            assert wizard._loaded_host_id != created
            # Select exposes its current value but not a public option list. Use the
            # repository's host count as a bound and navigate by keyboard until the
            # wizard's loaded identity reaches the created host.
            for _ in range(len(repo.list_hosts(project_id))):
                if wizard._loaded_host_id == created:
                    break
                await choose_option(pilot, "#guided-host-picker", steps_down=0, steps_up=1)
            await pilot.pause()
            assert wizard._loaded_host_id == created
            await click(pilot, "#guided-host-create")
            assert count() == base + 2, str(wizard.query_one("#wizard-status", Static).render())

    asyncio.run(run())


def test_picker_change_under_a_prompt_is_reverted_when_no_host_was_loaded(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await reach_hosts(pilot)
            wizard = app.screen
            project_id = wizard.context.project_id
            assert project_id is not None
            repo = app.composition.service.hosts(project_id)
            await click(pilot, "#guided-host-recommended")
            picker = wizard.query_one("#guided-host-picker", Select)
            # Seeded: a prompt pending while no host profile is loaded.
            wizard._loaded_host_id = None
            wizard._exit_confirmation_pending = True
            host_id = repo.list_hosts(project_id)[0].id
            with picker.prevent(Select.Changed):
                picker.value = Select.BLANK
            picker.value = host_id
            await pilot.pause()
            assert picker.value == Select.BLANK

    asyncio.run(run())
