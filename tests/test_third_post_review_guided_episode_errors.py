"""TPR-03: the guided wizard renders typed episode errors like the legacy screen and CLI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from guided_episode_support import _prepare_to_plan, _service_and_config
from textual.widgets import Input, Static

from deeper_dive.episode_config import (
    EpisodeConfigurationConflict,
    EpisodeConfigurationService,
)
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.run_repositories import GenerationRunRecord


def test_guided_save_of_a_frozen_episode_is_reported_not_raised(tmp_path: Path) -> None:
    asyncio.run(_scenario(tmp_path, frozen=True))


def test_guided_save_during_a_concurrent_edit_is_reported_not_raised(tmp_path: Path) -> None:
    asyncio.run(_scenario(tmp_path, frozen=False))


async def _scenario(tmp_path: Path, *, frozen: bool) -> None:
    service = _service_and_config(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        project_id, episode_id = await _prepare_to_plan(wizard, pilot)
        wizard.context.state = wizard.context.state.moved_to("episode")
        wizard._toggle()
        wizard._load_episode_form()
        configs = EpisodeConfigurationService(app.composition.database_for_project(project_id))
        before = service.hosts(project_id).get_episode(episode_id)

        wizard.query_one("#guided-episode-title", Input).value = "Edited title"
        wizard.query_one("#guided-episode-focus", Input).value = "Edited focus"
        if frozen:
            service.runs(project_id).create(
                GenerationRunRecord(
                    "run-1",
                    episode_id,
                    "sources",
                    "completed",
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                )
            )
            assert wizard.action_save_episode() is False
        else:
            with patch.object(
                EpisodeConfigurationService,
                "edit",
                side_effect=EpisodeConfigurationConflict("episode configuration changed; retry"),
            ):
                assert wizard.action_save_episode() is False

        assert app.is_running
        message = str(wizard.query_one("#guided-episode-validation", Static).render())
        assert message.startswith("Fix episode settings:")
        assert ("create a new episode" in message) if frozen else ("retry" in message)
        assert "Traceback" not in message
        assert wizard.query_one("#guided-episode-title", Input).value == "Edited title"
        assert service.hosts(project_id).get_episode(episode_id) == before
        assert configs.load_configuration(episode_id).title == before.title


def test_guided_save_reports_a_locked_database_instead_of_crashing(tmp_path: Path) -> None:
    import sqlite3

    async def scenario() -> None:
        service = _service_and_config(tmp_path)
        app = GuidedDeeperDiveApp(service)
        async with app.run_test(size=(100, 30)) as pilot:
            app.action_navigate("new")
            await pilot.pause()
            wizard = app.screen
            await _prepare_to_plan(wizard, pilot)
            wizard.context.state = wizard.context.state.moved_to("episode")
            wizard._toggle()
            wizard._load_episode_form()
            wizard.query_one("#guided-episode-title", Input).value = "Edited title"
            wizard.query_one("#guided-episode-focus", Input).value = "Edited focus"
            with patch.object(
                EpisodeConfigurationService,
                "edit",
                side_effect=sqlite3.OperationalError("database is locked"),
            ):
                assert wizard.action_save_episode() is False
            assert app.is_running
            message = str(wizard.query_one("#guided-episode-validation", Static).render())
            assert message.startswith("Fix episode settings:")
            assert wizard.query_one("#guided-episode-title", Input).value == "Edited title"

    asyncio.run(scenario())
