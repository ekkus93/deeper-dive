from __future__ import annotations

from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


class _TwoSegmentGenerator:
    def generate_plan(self, _request):
        return {
            "segments": [
                {
                    "title": "Opening",
                    "purpose": "Set context",
                    "target_duration_seconds": 600,
                    "questions": [],
                    "evidence_ids": [],
                    "lead_host_ids": [],
                },
                {
                    "title": "Deep Dive",
                    "purpose": "Explore evidence",
                    "target_duration_seconds": 600,
                    "questions": [],
                    "evidence_ids": [],
                    "lead_host_ids": [],
                },
            ]
        }


def _episode_fixture(
    tmp_path: Path,
) -> tuple[DeeperDiveService, str, str, tuple[str, str]]:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Dirty navigation")
    repository = service.hosts(project.id)
    host_ids = ("host-one", "host-two")
    for host_id, name in zip(host_ids, ("Host One", "Host Two"), strict=True):
        repository.create_host(HostProfile(host_id, project.id, name).to_record())
    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project.id) / "project.db")
    )
    episode = configs.create(
        project.id,
        EpisodeConfiguration(
            title="Durable title",
            focus="Durable focus",
            target_duration_seconds=1200,
            host_ids=host_ids,
        ),
    )
    return service, project.id, episode.id, host_ids
