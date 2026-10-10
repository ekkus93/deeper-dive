"""Regression coverage for Quick Deep Dive research default precedence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.research_policy import ResearchPolicyStore
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import UserConfig, UserConfigStore


@pytest.mark.parametrize("global_mode", ["off", "useful", "aggressive"])
def test_global_research_default_survives_restart(tmp_path: Path, global_mode: str) -> None:
    data_dir = tmp_path / "data"
    service = DeeperDiveService(WorkspaceManager(data_dir))
    project = service.create_project("Global research")
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(defaults={"research_policy": global_mode})
    )

    restarted = DeeperDiveService(WorkspaceManager(data_dir))
    episode = restarted.quick_deep_dive(project.id)
    database = Database(restarted.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    assert config.research_overrides["policy"] == global_mode
    assert ResearchPolicyStore(database).episode(project.id, episode.id).mode.value == global_mode


@pytest.mark.parametrize(
    ("global_mode", "quick_mode", "project_mode", "expected"),
    [
        ("aggressive", None, None, "aggressive"),
        ("aggressive", "off", None, "off"),
        ("aggressive", "off", "useful", "useful"),
        ("off", "aggressive", None, "aggressive"),
        ("off", "", None, "off"),
    ],
)
def test_research_precedence(
    tmp_path: Path,
    global_mode: str,
    quick_mode: str | None,
    project_mode: str | None,
    expected: str,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    instructions = (
        json.dumps({"quick_deep_dive": {"research_policy": project_mode}})
        if project_mode is not None
        else ""
    )
    project = service.create_project("Precedence", instructions=instructions)
    defaults = {"research_policy": global_mode}
    if quick_mode is not None:
        defaults["quick_deep_dive_research_policy"] = quick_mode
    UserConfigStore(service.workspaces.data_dir / "config.json").save(
        UserConfig(defaults=defaults)
    )
    episode = service.quick_deep_dive(project.id)
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    assert config.research_overrides["policy"] == expected
    assert ResearchPolicyStore(database).episode(project.id, episode.id).mode.value == expected
