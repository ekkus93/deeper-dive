"""6PR-04: a no-op Save keeps an empty stored depth, audience or project audience.

Resume goes through ``app.action_navigate("resume")`` (a fresh data directory starts in
first-run setup, so Home's Resume button is not reachable without a live provider);
everything after that is real input.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from guided_pilot import click, continue_step, reach_hosts, type_into
from test_fifth_post_review_stored_values_preserved import _app, _save_and_exit
from textual.widgets import Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_new_deep_dive import GuidedProjectWizard
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


def test_empty_depth_and_audience_survive_a_title_only_save(tmp_path: Path) -> None:
    asyncio.run(_episode_scenario(tmp_path))


async def _episode_scenario(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = _app(data)
    async with first.run_test(size=(100, 45)) as pilot:
        await reach_hosts(pilot)
        wizard = first.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        await click(pilot, "#guided-host-recommended")
        await click(pilot, "#guided-host-order-save")
        await click(pilot, "#guided-host-down")
        episode_id = wizard.context.episode_id
        project_id = wizard.context.project_id
        assert episode_id is not None and project_id is not None
        await _save_and_exit(pilot, wizard)

    service = DeeperDiveService(WorkspaceManager(data))
    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
    config, revision = configs.load_with_revision(episode_id)
    # The CLI (`episode configure --depth "" --audience " "`) stores empty text.
    configs.edit(
        episode_id, replace(config, technical_depth="", audience=""), expected_revision=revision
    )
    assert configs.load_configuration(episode_id).audience == ""

    second = _app(data)
    async with second.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        second.action_navigate("resume")
        await pilot.pause()
        await pilot.pause()
        resumed = second.screen
        assert isinstance(resumed, GuidedEpisodeWizard)
        await continue_step(pilot, "episode")
        assert resumed.query_one("#guided-episode-audience", Select).value == ""
        assert resumed.query_one("#guided-episode-depth", Select).value == ""
        await type_into(pilot, "#guided-episode-title", "Only the title changed")
        await type_into(pilot, "#guided-episode-focus", "Real focus question")
        await click(pilot, "#guided-episode-save")

    stored = configs.load_configuration(episode_id)
    assert stored.title == "Only the title changed"
    assert stored.audience == ""
    assert stored.technical_depth == ""


def test_empty_project_audience_survives_a_description_only_save(tmp_path: Path) -> None:
    asyncio.run(_project_scenario(tmp_path))


async def _project_scenario(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = _app(data)
    async with first.run_test(size=(100, 45)) as pilot:
        first._first_run_readiness.close()
        await pilot.pause()
        first.action_navigate("new")
        await pilot.pause()
        wizard = first.screen
        assert isinstance(wizard, GuidedProjectWizard)
        await type_into(pilot, "#guided-project-name", "Policy")
        await type_into(pilot, "#guided-project-topic", "Does typing work")
        await click(pilot, "#guided-project-create")
        project_id = wizard.context.project_id
        assert project_id is not None
        await _save_and_exit(pilot, wizard)

    service = DeeperDiveService(WorkspaceManager(data))
    project = service.open_project(project_id)
    assert project is not None
    service.update_project(
        project_id, project.name, instructions="Main curiosity: Does typing work\nAudience: "
    )

    second = _app(data)
    async with second.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        second.action_navigate("resume")
        await pilot.pause()
        await pilot.pause()
        resumed = second.screen
        assert isinstance(resumed, GuidedProjectWizard)
        assert resumed.query_one("#guided-project-audience", Select).value == ""
        await type_into(pilot, "#guided-project-description", "Added later")
        await click(pilot, "#guided-project-create")

    stored = service.open_project(project_id)
    assert stored is not None
    assert "Audience: general" not in stored.instructions
    assert "Description: Added later" in stored.instructions
