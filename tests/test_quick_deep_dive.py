from __future__ import annotations

import asyncio
import json
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.hosts import HostProfile
from deeper_dive.preflight_screen import PreflightScreen
from deeper_dive.research_policy import ResearchMode, ResearchPolicyStore
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfig, UserConfigStore


def _episode_host_presets(
    service: DeeperDiveService, project_id: str, host_ids: tuple[str, ...]
) -> tuple[str | None, ...]:
    hosts = {host.id: host for host in service.hosts(project_id).list_hosts(project_id)}
    return tuple(hosts[host_id].preset_origin for host_id in host_ids)


def test_quick_deep_dive_creates_normal_episode_with_default_hosts_and_useful_policy(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick")

    episode = service.quick_deep_dive(project.id)

    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    policy = ResearchPolicyStore(database).episode(project.id, episode.id)
    assert config.title == "Quick Deep Dive"
    assert config.target_duration_seconds == 1200
    assert config.research_overrides["policy"] == "useful"
    assert _episode_host_presets(service, project.id, config.host_ids) == (
        "curious_explainer",
        "skeptic",
    )
    assert policy.mode is ResearchMode.USEFUL


def test_quick_deep_dive_uses_existing_project_hosts_as_defaults(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick with hosts")
    service.hosts(project.id).create_host(HostProfile("h1", project.id, "Existing One").to_record())
    service.hosts(project.id).create_host(HostProfile("h2", project.id, "Existing Two").to_record())
    service.hosts(project.id).create_host(
        HostProfile("h3", project.id, "Existing Three").to_record()
    )

    episode = service.quick_deep_dive(project.id)

    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    assert config.host_ids == ("h1", "h3")
    assert len(service.hosts(project.id).list_hosts(project.id)) == 3


def test_quick_deep_dive_user_defaults_override_builtins(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick configured")
    UserConfigStore(service.workspaces.data_dir / "config.json").save(
        UserConfig(
            defaults={
                "quick_deep_dive_duration_minutes": "12",
                "quick_deep_dive_host_presets": "skeptic,curious_explainer",
                "quick_deep_dive_research_policy": "off",
            }
        )
    )

    episode = service.quick_deep_dive(project.id)
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    assert config.target_duration_seconds == 720
    assert config.research_overrides["policy"] == "off"
    assert _episode_host_presets(service, project.id, config.host_ids) == (
        "skeptic",
        "curious_explainer",
    )


def test_quick_deep_dive_project_overrides_take_precedence(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project(
        "Quick project override",
        instructions=json.dumps(
            {
                "quick_deep_dive": {
                    "duration_minutes": 7,
                    "host_presets": "curious_explainer,skeptic",
                    "research_policy": "useful",
                }
            }
        ),
    )
    UserConfigStore(service.workspaces.data_dir / "config.json").save(
        UserConfig(
            defaults={
                "quick_deep_dive_duration_minutes": "12",
                "quick_deep_dive_host_presets": "skeptic,curious_explainer",
                "quick_deep_dive_research_policy": "off",
            }
        )
    )

    episode = service.quick_deep_dive(project.id)
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    assert config.target_duration_seconds == 420
    assert config.research_overrides["policy"] == "useful"
    assert _episode_host_presets(service, project.id, config.host_ids) == (
        "curious_explainer",
        "skeptic",
    )


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
