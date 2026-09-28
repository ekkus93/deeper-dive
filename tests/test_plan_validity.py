from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from deeper_dive.domain.clock import FrozenClock
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.plan_validity import evaluate_episode_plan
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)


def _fixture(tmp_path):
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p1", "Project", "now", "now"))
    corpus.create_project(ProjectRecord("p2", "Other", "now", "now"))
    hosts = HostEpisodeRepository(database)
    hosts.create_host(create_host_from_preset("skeptic", "p1", host_id="h1").to_record())
    hosts.create_host(create_host_from_preset("moderator", "p1", host_id="h2").to_record())
    hosts.create_host(create_host_from_preset("skeptic", "p2", host_id="foreign-host").to_record())
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
    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
    episodes = EpisodeConfigurationService(database, clock=clock)
    episode = episodes.create(
        "p1",
        EpisodeConfiguration(
            title="Episode",
            target_duration_seconds=600,
            host_ids=("h1", "h2"),
        ),
    )
    other = episodes.create(
        "p1",
        EpisodeConfiguration(
            title="Other",
            target_duration_seconds=600,
            host_ids=("h1",),
        ),
    )
    return database, hosts, episode.id, other.id


def _save(
    hosts: HostEpisodeRepository,
    episode_id: str,
    *,
    status: str = "draft",
    plan_json: str = "{}",
    ordinal: int = 0,
    title: str = "Segment",
    duration: int = 600,
    segment_json: str | None = None,
    with_segment: bool = True,
) -> None:
    plan = EpisodePlanRecord("plan-1", episode_id, "now", "now", status, plan_json)
    segments = []
    if with_segment:
        payload = (
            segment_json
            if segment_json is not None
            else json.dumps(
                {
                    "title": title,
                    "target_duration_seconds": duration,
                    "lead_host_ids": ["h1"],
                    "evidence_ids": ["e1"],
                }
            )
        )
        segments.append(
            SegmentPlanRecord(
                "segment-1",
                plan.id,
                ordinal,
                title,
                "purpose",
                duration,
                payload,
            )
        )
    hosts.save_plan(plan, segments)


def test_valid_plan_is_usable(tmp_path) -> None:
    database, hosts, episode_id, _ = _fixture(tmp_path)
    _save(hosts, episode_id)
    result = evaluate_episode_plan(database, episode_id)
    assert result.usable
    assert result.segment_count == 1


@pytest.mark.parametrize(
    ("mutation", "issue"),
    [
        ({"with_segment": False}, "plan has no segments"),
        ({"plan_json": "{"}, "plan JSON is invalid"),
        ({"plan_json": "[]"}, "plan JSON payload must be an object"),
        ({"status": "rejected"}, "is not usable for generation"),
        ({"ordinal": 2}, "ordinal 2 is not coherent"),
        ({"title": ""}, "requires a non-empty title"),
        ({"duration": 0}, "duration must be positive"),
        (
            {
                "segment_json": json.dumps(
                    {
                        "title": "Segment",
                        "target_duration_seconds": 600,
                        "lead_host_ids": ["foreign-host"],
                    }
                )
            },
            "outside the episode",
        ),
        (
            {
                "segment_json": json.dumps(
                    {
                        "title": "Segment",
                        "target_duration_seconds": 600,
                        "evidence_ids": ["foreign-evidence"],
                    }
                )
            },
            "outside scope",
        ),
        ({"segment_json": "{"}, "JSON is invalid"),
    ],
)
def test_invalid_persisted_plan_matrix(tmp_path, mutation, issue) -> None:
    database, hosts, episode_id, _ = _fixture(tmp_path)
    _save(hosts, episode_id, **mutation)
    result = evaluate_episode_plan(database, episode_id)
    assert not result.usable
    assert any(issue in message for message in result.issues)


def test_plan_for_another_episode_does_not_satisfy_selected_episode(tmp_path) -> None:
    database, hosts, episode_id, other_id = _fixture(tmp_path)
    _save(hosts, other_id)
    result = evaluate_episode_plan(database, episode_id)
    assert not result.usable
    assert result.plan_id is None
