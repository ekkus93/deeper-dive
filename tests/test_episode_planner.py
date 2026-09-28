from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deeper_dive.domain.clock import FrozenClock
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlannerService, PlannedSegment
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)


class FakePlanner:
    def __init__(self) -> None:
        self.calls = 0
        self.regeneration_evidence_ids: list[str] = []

    def generate_plan(self, request):
        self.calls += 1
        if request.get("mode") == "regenerate_segment":
            return {
                "segments": [
                    {
                        "title": "Revised",
                        "purpose": "repair",
                        "target_duration_seconds": 300,
                        "lead_host_ids": ["h1"],
                        "evidence_ids": self.regeneration_evidence_ids,
                    }
                ]
            }
        return {
            "segments": [
                {
                    "title": "Context",
                    "purpose": "orient",
                    "target_duration_seconds": 100,
                    "lead_host_ids": ["h1"],
                },
                {
                    "title": "Analysis",
                    "purpose": "explain",
                    "target_duration_seconds": 100,
                    "lead_host_ids": ["h2"],
                },
            ]
        }


def _service(tmp_path):
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p1", "Project", "now", "now"))
    corpus.create_project(ProjectRecord("p2", "Other", "now", "now"))
    corpus.create_source(
        SourceRecord(
            "s1",
            "p1",
            "user",
            "pasted",
            "Source",
            "now",
            included=True,
            status="indexed",
        )
    )
    corpus.create_chunk(SourceChunkRecord("e1", "s1", 0, "evidence", "hash"))
    corpus.create_source(
        SourceRecord(
            "s2",
            "p2",
            "user",
            "pasted",
            "Foreign",
            "now",
            included=True,
            status="indexed",
        )
    )
    corpus.create_chunk(SourceChunkRecord("foreign-evidence", "s2", 0, "foreign", "hash2"))
    hosts = HostEpisodeRepository(database)
    hosts.create_host(create_host_from_preset("skeptic", "p1", host_id="h1").to_record())
    hosts.create_host(create_host_from_preset("moderator", "p1", host_id="h2").to_record())
    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
    episode = EpisodeConfigurationService(database, clock=clock).create(
        "p1",
        EpisodeConfiguration(
            title="Episode", focus="", target_duration_seconds=600, host_ids=("h1", "h2")
        ),
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


def test_segment_edit_rejects_nonexistent_and_cross_project_evidence(tmp_path) -> None:
    service, episode_id, _ = _service(tmp_path)
    service.build_plan(episode_id)

    for evidence_id in ("missing", "foreign-evidence"):
        segment = PlannedSegment(
            "Edited",
            "repair",
            300,
            evidence_ids=(evidence_id,),
            lead_host_ids=("h1",),
        )
        with pytest.raises(ValueError, match="evidence outside retrieved evidence"):
            service.edit_segment(episode_id, 0, segment)


def test_segment_edit_preserves_valid_episode_evidence(tmp_path) -> None:
    service, episode_id, _ = _service(tmp_path)
    service.build_plan(episode_id)
    segment = PlannedSegment(
        "Edited",
        "repair",
        300,
        evidence_ids=("e1",),
        lead_host_ids=("h1",),
    )
    revised = service.edit_segment(episode_id, 0, segment)
    assert revised.segments[0].evidence_ids == ("e1",)


def test_segment_regeneration_rejects_out_of_scope_evidence(tmp_path) -> None:
    service, episode_id, fake = _service(tmp_path)
    service.build_plan(episode_id)
    fake.regeneration_evidence_ids = ["foreign-evidence"]
    with pytest.raises(ValueError, match="evidence outside retrieved evidence"):
        service.regenerate_segment(episode_id, 0)


def test_evidence_validation_disabled_is_explicit_and_empty_scope_rejects() -> None:
    raw = {
        "segments": [
            {
                "title": "Segment",
                "target_duration_seconds": 60,
                "evidence_ids": ["unknown"],
            }
        ]
    }
    assert EpisodePlannerService._validate_segments(raw, (), None)[0].evidence_ids == ("unknown",)
    with pytest.raises(ValueError, match="evidence outside retrieved evidence"):
        EpisodePlannerService._validate_segments(raw, (), set())
