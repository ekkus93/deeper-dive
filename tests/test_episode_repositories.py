from __future__ import annotations

from pathlib import Path

from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    EpisodeRecord,
    HostEpisodeRepository,
    HostProfileRecord,
    HostRelationshipRecord,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord


def _project(corpus: CorpusRepository) -> ProjectRecord:
    project = ProjectRecord(
        id="project-1",
        name="Corpus",
        created_at="2026-09-17T20:00:00Z",
        modified_at="2026-09-17T20:00:00Z",
    )
    corpus.create_project(project)
    return project


def test_hosts_relationships_and_ordered_episode_membership_round_trip(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    project = _project(corpus)
    repository = HostEpisodeRepository(database)

    hosts = [
        HostProfileRecord("host-a", project.id, "Ada", role="explainer"),
        HostProfileRecord("host-b", project.id, "Bert", role="skeptic"),
        HostProfileRecord("host-c", project.id, "Cy", role="synthesizer"),
    ]
    for host in hosts:
        repository.create_host(host)

    relationships = [
        HostRelationshipRecord(project.id, "host-a", "host-b", '{"rapport":"warm"}'),
        HostRelationshipRecord(project.id, "host-b", "host-c", '{"stance":"probing"}'),
        HostRelationshipRecord(project.id, "host-c", "host-a", '{"trust":0.8}'),
    ]
    for relationship in relationships:
        repository.upsert_relationship(relationship)

    episode = EpisodeRecord(
        id="episode-1",
        project_id=project.id,
        title="Roundtable",
        focus="Evidence",
        audience="technical",
        technical_depth="advanced",
        target_duration_seconds=1200,
        style="roundtable",
        config_json='{"research":"useful"}',
        created_at="2026-09-17T20:01:00Z",
        modified_at="2026-09-17T20:01:00Z",
    )
    repository.create_episode(episode, ["host-c", "host-a", "host-b"])

    assert repository.list_hosts(project.id) == hosts
    assert repository.list_relationships(project.id) == relationships
    assert repository.get_episode(episode.id) == episode
    assert repository.list_episode_host_ids(episode.id) == ["host-c", "host-a", "host-b"]


def test_multiple_episodes_share_project_corpus_but_keep_independent_hosts(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    project = _project(corpus)
    repository = HostEpisodeRepository(database)
    for host_id in ("host-a", "host-b", "host-c"):
        repository.create_host(HostProfileRecord(host_id, project.id, host_id.upper()))

    first = EpisodeRecord(
        "episode-1",
        project.id,
        "First",
        "2026-09-17T20:01:00Z",
        "2026-09-17T20:01:00Z",
    )
    second = EpisodeRecord(
        "episode-2",
        project.id,
        "Second",
        "2026-09-17T20:02:00Z",
        "2026-09-17T20:02:00Z",
    )
    repository.create_episode(first, ["host-a", "host-b"])
    repository.create_episode(second, ["host-c", "host-a"])

    assert repository.list_episodes(project.id) == [first, second]
    assert repository.list_episode_host_ids(first.id) == ["host-a", "host-b"]
    assert repository.list_episode_host_ids(second.id) == ["host-c", "host-a"]


def test_episode_plan_and_ordered_segments_round_trip(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    project = _project(corpus)
    repository = HostEpisodeRepository(database)
    host = HostProfileRecord("host-a", project.id, "Ada")
    repository.create_host(host)
    episode = EpisodeRecord(
        "episode-1",
        project.id,
        "Plan",
        "2026-09-17T20:01:00Z",
        "2026-09-17T20:01:00Z",
    )
    repository.create_episode(episode, [host.id])

    plan = EpisodePlanRecord(
        "plan-1",
        episode.id,
        "2026-09-17T20:02:00Z",
        "2026-09-17T20:02:00Z",
        plan_json='{"goal":"explain"}',
    )
    segments = [
        SegmentPlanRecord("segment-b", plan.id, 1, "Second", target_duration_seconds=300),
        SegmentPlanRecord("segment-a", plan.id, 0, "First", target_duration_seconds=240),
    ]
    repository.save_plan(plan, segments)

    assert repository.get_plan(episode.id) == plan
    assert repository.list_segments(plan.id) == [segments[1], segments[0]]
