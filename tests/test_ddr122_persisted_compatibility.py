from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.provider_factory import ProviderConfigurationError, ProviderFactory
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import UserConfigStore


def test_existing_project_and_episode_reload_from_persisted_workspace(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    service = DeeperDiveService(WorkspaceManager(data_dir))
    service.workspaces.initialize()
    project = service.create_project("Persisted project")
    episode = EpisodeConfigurationService(
        service.hosts(project.id).database
    ).create(project.id, EpisodeConfiguration(title="Persisted episode"))

    restarted = DeeperDiveService(WorkspaceManager(data_dir))
    restarted.workspaces.initialize()

    loaded_project = restarted.open_project(project.id)
    loaded_episode = restarted.hosts(project.id).get_episode(episode.id)
    assert loaded_project is not None
    assert loaded_project.name == "Persisted project"
    assert loaded_episode is not None
    assert loaded_episode.title == "Persisted episode"


def test_existing_concrete_provider_config_loads_and_builds(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {
                    "planner": {
                        "provider_type": "fake",
                        "default_model": "fake-v1",
                    },
                    "speech": {"provider_type": "fake-tts"},
                },
                "defaults": {"host_generation": "planner"},
            }
        ),
        encoding="utf-8",
    )

    config = UserConfigStore(path).load()
    built = ProviderFactory(environ={}).build(config)
    assert built.llm_registry.provider_ids() == ("planner",)
    assert built.tts_registry.provider_ids() == ("speech",)
    assert config.defaults["host_generation"] == "planner"


@pytest.mark.parametrize("legacy_type", ["llm", "tts"])
def test_ambiguous_legacy_provider_type_has_actionable_upgrade_guidance(
    tmp_path: Path, legacy_type: str
) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {"legacy": {"provider_type": legacy_type}},
                "defaults": {},
            }
        ),
        encoding="utf-8",
    )

    config = UserConfigStore(path).load()
    with pytest.raises(ProviderConfigurationError) as captured:
        ProviderFactory(environ={}).build(config)

    message = str(captured.value)
    assert "ambiguous" in message
    assert "concrete adapter type" in message
    assert legacy_type in message
