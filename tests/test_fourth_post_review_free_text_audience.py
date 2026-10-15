"""FPR-03: a free-text episode audience (CLI / legacy setup) must not crash guided resume."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from guided_pilot import click, continue_step, reach_hosts, type_into, wait_until
from textual.widgets import Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager

FREE_TEXT = "college students"


def _app(data: Path) -> GuidedDeeperDiveApp:
    return GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(data)))


def test_resume_with_free_text_audience_keeps_the_value(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = _app(data)
    async with first.run_test(size=(100, 45)) as pilot:
        await reach_hosts(pilot)
        wizard = first.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        await click(pilot, "#guided-host-recommended")
        await click(pilot, "#guided-host-order-save")
        await click(pilot, "#guided-host-down")  # unsaved order edit -> prompt on exit
        episode_id = wizard.context.episode_id
        project_id = wizard.context.project_id
        assert episode_id is not None and project_id is not None
        await pilot.press("escape")
        await wait_until(pilot, lambda: wizard._exit_confirmation_pending)
        await click(pilot, "#wizard-confirm-save")
        assert wizard.save_exit_requested

    # Another surface (CLI / legacy Episode Setup) stores a free-text audience.
    service = DeeperDiveService(WorkspaceManager(data))
    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
    config, revision = configs.load_with_revision(episode_id)
    configs.edit(episode_id, replace(config, audience=FREE_TEXT), expected_revision=revision)
    stored = configs.load_configuration(episode_id)
    assert stored.audience == FREE_TEXT

    second = _app(data)
    async with second.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        # A fresh data directory starts in first-run setup, so Home's Resume button is
        # not reachable without a live provider; the app's own routing entry is used.
        second.action_navigate("resume")
        await pilot.pause()
        await pilot.pause()
        assert second.is_running
        resumed = second.screen
        assert isinstance(resumed, GuidedEpisodeWizard)
        audience = resumed.query_one("#guided-episode-audience", Select)
        assert audience.value == FREE_TEXT
        # Opening the form is not an edit, and the durable value is untouched.
        assert configs.load_configuration(episode_id).audience == FREE_TEXT
        # 5PR-11: the spec's acceptance step, a no-op Save of the audience. Only the
        # title changes; the free-text audience must survive the Save.
        await continue_step(pilot, "episode")
        await type_into(pilot, "#guided-episode-title", "Retitled")
        await type_into(pilot, "#guided-episode-focus", "A focus question")
        await click(pilot, "#guided-episode-save")
        saved = configs.load_configuration(episode_id)
        assert saved.title == "Retitled"
        assert saved.audience == FREE_TEXT
