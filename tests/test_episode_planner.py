from __future__ import annotations

from datetime import UTC, datetime

from deeper_dive.domain.clock import FrozenClock
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord


class FakePlanner:
    def __init__(self) -> None:
        self.calls = 0

    def generate_plan(self, request):
        self.calls += 1
        if request.get("mode") == "regenerate_segment":
            return {"segments": [{"title": "Revised", "purpose": "repair", "target_duration_seconds": 300, "lead_host_ids": ["h1"]}]}
        return {"segments": [
            {"title": "Context", "purpose": "orient", "target_duration_seconds": 100, "lead_host_ids": ["h1"]},
            {"title": "Analysis", "purpose": "explain", "target_duration_seconds": 100, "lead_host_ids": ["h2"]},
        ]}


def _service(tmp_path):
    database = Database(tmp_path / "project.db")
    CorpusRepository(database).create_project(ProjectRecord("p1", "Project", "now", "now"))
    hosts = HostEpisodeRepository(database)
    hosts.create_host(create_host_from_preset("skeptic", "p1", host_id="h1").to_record())
    hosts.create_host(create_host_from_preset("moderator", "p1", host_id="h2").to_record())
    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
    episode = EpisodeConfigurationService(database, clock=clock).create(
        "p1",
        EpisodeConfiguration(title="Episode", focus="", target_duration_seconds=600, host_ids=("h1", "h2")),
    )
    fake = FakePlanner()
    return EpisodePlannerService(database, fake, clock=clock), episode.id, fake


def test_plan_is_duration_bounded_persisted_and_reloadable(tmp_path) -> None:
    service, episode_id, _ = _service(tmp_path)
    plan = service.build_plan(episode_id)
    assert plan.target_duration_seconds == 600
    assert [segment.target_duration_seconds for segment in plan.segments] == [300, 300]
    assert service.load_plan(episode_id) == plan


def test_targeted_segment_regeneration_preserves_other_segment(tmp_path) -> None:
    service, episode_id, fake = _service(tmp_path)
    original = service.build_plan(episode_id)
    revised = service.regenerate_segment(episode_id, 1)
    assert fake.calls == 2
    assert revised.segments[0].title == original.segments[0].title
    assert revised.segments[1].title == "Revised"
    assert revised.target_duration_seconds == 600
