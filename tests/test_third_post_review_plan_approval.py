"""TPR-04: plan approval is compare-and-swapped and preserves plan identity."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import (
    EpisodeConfiguration,
    EpisodeConfigurationConflict,
    EpisodeConfigurationService,
)
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.workspace import WorkspaceManager


class _Generator:
    def generate_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "segments": [
                {
                    "title": "Opening",
                    "purpose": "p",
                    "target_duration_seconds": 600,
                    "lead_host_ids": ["h1"],
                }
            ]
        }


def _setup(
    tmp_path: Path,
) -> tuple[EpisodeConfigurationService, EpisodePlannerService, Database, str]:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("P")
    for host_id, name in (("h1", "A"), ("h2", "B")):
        service.hosts(project.id).create_host(HostProfile(host_id, project.id, name).to_record())
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    configurations = EpisodeConfigurationService(database)
    episode = configurations.create(
        project.id,
        EpisodeConfiguration(title="T", target_duration_seconds=600, host_ids=("h1",)),
    )
    planner = EpisodePlannerService(database, _Generator())
    planner.build_plan(episode.id)
    return configurations, planner, database, episode.id


def test_approval_after_concurrent_edit_fails_and_does_not_resurrect_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configurations, planner, database, episode_id = _setup(tmp_path)
    repository = HostEpisodeRepository(database)
    original_load = planner.load_plan

    def load_then_edit(eid: str) -> Any:
        plan = original_load(eid)
        # Deterministic race: the episode is edited between load and approval.
        configurations.edit(
            eid,
            replace(
                configurations.load_configuration(eid),
                host_ids=("h2",),
                target_duration_seconds=3000,
            ),
        )
        return plan

    monkeypatch.setattr(planner, "load_plan", load_then_edit)
    with pytest.raises(EpisodeConfigurationConflict):
        planner.approve_plan(episode_id)

    assert repository.get_plan(episode_id) is None
    assert configurations.load_configuration(episode_id).host_ids == ("h2",)


def test_approval_preserves_plan_and_segment_identity(tmp_path: Path) -> None:
    _configurations, planner, database, episode_id = _setup(tmp_path)
    repository = HostEpisodeRepository(database)
    before = repository.get_plan(episode_id)
    assert before is not None
    segment_ids = [item.id for item in repository.list_segments(before.id)]

    planner.approve_plan(episode_id)

    after = repository.get_plan(episode_id)
    assert after is not None
    assert after.id == before.id
    assert after.status == "approved"
    assert [item.id for item in repository.list_segments(after.id)] == segment_ids
