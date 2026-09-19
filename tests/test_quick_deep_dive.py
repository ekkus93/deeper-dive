from __future__ import annotations

import asyncio
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.hosts import HostProfile
from deeper_dive.preflight_screen import PreflightScreen
from deeper_dive.research_policy import ResearchMode, ResearchPolicyStore
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def test_quick_deep_dive_creates_normal_episode_with_default_hosts_and_useful_policy(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick")

    episode = service.quick_deep_dive(project.id)

    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    hosts = service.hosts(project.id).list_hosts(project.id)
    policy = ResearchPolicyStore(database).episode(project.id, episode.id)
    assert config.title == "Quick Deep Dive"
    assert config.target_duration_seconds == 1200
    assert config.research_overrides["policy"] == "useful"
    assert tuple(host.preset_origin for host in hosts) == ("curious_explainer", "skeptic")
    assert config.host_ids == tuple(host.id for host in hosts)
    assert policy.mode is ResearchMode.USEFUL


def test_quick_deep_dive_uses_existing_project_hosts_as_defaults(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick with hosts")
    service.hosts(project.id).create_host(HostProfile("h1", project.id, "Existing One").to_record())
    service.hosts(project.id).create_host(HostProfile("h2", project.id, "Existing Two").to_record())
    service.hosts(project.id).create_host(HostProfile("h3", project.id, "Existing Three").to_record())

    episode = service.quick_deep_dive(project.id)

    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    assert config.host_ids == ("h1", "h2")
    assert len(service.hosts(project.id).list_hosts(project.id)) == 3


def test_quick_deep_dive_tui_action_reaches_preflight(tmp_path: Path) -> None:
    asyncio.run(_exercise_quick_tui(tmp_path))


async def _exercise_quick_tui(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick TUI")
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("episode")
        await pilot.pause()
        app.screen.action_quick_deep_dive()
        await pilot.pause()
        assert isinstance(app.screen, PreflightScreen)
        assert app.current_episode_id is not None

    episode = service.hosts(project.id).list_episodes(project.id)[0]
    assert episode.title == "Quick Deep Dive"
