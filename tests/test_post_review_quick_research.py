"""Post-review regression coverage for durable Quick research precedence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.research_policy import ResearchMode, ResearchPolicyStore
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import UserConfig, UserConfigStore


def _quick_policy(service: DeeperDiveService, project_id: str) -> tuple[str, ResearchMode]:
    episode = service.quick_deep_dive(project_id)
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    policy = ResearchPolicyStore(database).episode(project_id, episode.id)
    return config.research_overrides["policy"], policy.mode


@pytest.mark.parametrize("mode", ["off", "useful", "aggressive"])
def test_global_research_default_applies_to_quick_without_specific_override(
    tmp_path: Path, mode: str
) -> None:
    data_dir = tmp_path / "data"
    service = DeeperDiveService(WorkspaceManager(data_dir))
    project = service.create_project("Global research default")
    UserConfigStore(data_dir / "config.json").save(UserConfig(defaults={"research_policy": mode}))

    assert _quick_policy(service, project.id) == (mode, ResearchMode(mode))

    # No in-memory cache may be required for global research precedence.
    restarted = DeeperDiveService(WorkspaceManager(data_dir))
    assert _quick_policy(restarted, project.id) == (mode, ResearchMode(mode))


@pytest.mark.parametrize(
    ("global_mode", "quick_mode"),
    [("off", "aggressive"), ("aggressive", "off")],
)
def test_explicit_user_quick_override_beats_global_default(
    tmp_path: Path, global_mode: str, quick_mode: str
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("User Quick override")
    UserConfigStore(service.workspaces.data_dir / "config.json").save(
        UserConfig(
            defaults={
                "research_policy": global_mode,
                "quick_deep_dive_research_policy": quick_mode,
            }
        )
    )

    assert _quick_policy(service, project.id) == (quick_mode, ResearchMode(quick_mode))


def test_project_quick_override_beats_user_quick_and_global_defaults(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project(
        "Project Quick override",
        instructions=json.dumps({"quick_deep_dive": {"research_policy": "useful"}}),
    )
    UserConfigStore(service.workspaces.data_dir / "config.json").save(
        UserConfig(
            defaults={
                "research_policy": "off",
                "quick_deep_dive_research_policy": "aggressive",
            }
        )
    )

    assert _quick_policy(service, project.id) == ("useful", ResearchMode.USEFUL)
    restarted = DeeperDiveService(WorkspaceManager(service.workspaces.data_dir))
    assert _quick_policy(restarted, project.id) == ("useful", ResearchMode.USEFUL)
