"""Project Quick overrides must validate before mutating durable project state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize(
    "presets",
    (
        "skeptic,unknown_preset",
        "unknown_preset,skeptic",
        "skeptic,",
    ),
)
def test_invalid_project_quick_host_presets_never_create_partial_hosts(
    tmp_path: Path, presets: str
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project(
        "Project with invalid Quick presets",
        instructions=json.dumps({"quick_deep_dive": {"host_presets": presets}}),
    )
    repository = service.hosts(project.id)
    assert repository.list_hosts(project.id) == []
    assert repository.list_episodes(project.id) == []

    with pytest.raises(ValueError, match="exactly two valid host presets"):
        service.quick_deep_dive(project.id)

    # In particular, a valid first preset must not be created before the
    # invalid second preset is rejected. Retry/restart remains possible.
    assert repository.list_hosts(project.id) == []
    assert repository.list_episodes(project.id) == []


def test_valid_project_quick_host_presets_still_create_two_hosts(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project(
        "Valid Quick presets",
        instructions=json.dumps(
            {"quick_deep_dive": {"host_presets": "skeptic,domain_expert"}}
        ),
    )
    episode = service.quick_deep_dive(project.id)
    repository = service.hosts(project.id)
    host_ids = repository.list_episode_host_ids(episode.id)
    hosts = {host.id: host for host in repository.list_hosts(project.id)}
    assert tuple(hosts[host_id].preset_origin for host_id in host_ids) == (
        "skeptic",
        "domain_expert",
    )
    assert len(repository.list_episodes(project.id)) == 1
