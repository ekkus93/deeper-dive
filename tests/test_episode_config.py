from __future__ import annotations

from datetime import UTC, datetime

from deeper_dive.domain.clock import FixedClock
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord


def test_episode_configurations_are_independent_reproducible_snapshots(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    CorpusRepository(database).create_project(ProjectRecord("p1", "Project", "now", "now"))
    hosts = HostEpisodeRepository(database)
    first = create_host_from_preset("skeptic", "p1", host_id="h1")
    second = create_host_from_preset("moderator", "p1", host_id="h2")
    hosts.create_host(first.to_record())
    hosts.create_host(second.to_record())
    service = EpisodeConfigurationService(
        database, clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    )

    one_config = EpisodeConfiguration(
        title="Deep technical",
        focus="mechanisms",
        audience="experts",
        technical_depth="deep",
        target_duration_seconds=1200,
        style="debate",
        host_ids=("h1", "h2"),
        must_cover=("methods",),
        avoid_topics=("speculation",),
        source_overrides={"source-a": False},
        research_overrides={"mode": "conservative"},
        model_overrides={"directing": {"provider": "openai", "model": "model-a"}},
    )
    two_config = EpisodeConfiguration(
        title="Accessible overview",
        focus="implications",
        host_ids=("h2",),
        research_overrides={"mode": "off"},
        model_overrides={"directing": {"provider": "ollama", "model": "model-b"}},
    )
    one = service.create("p1", one_config)
    two = service.create("p1", two_config)

    assert service.load_configuration(one.id) == one_config
    assert service.load_configuration(two.id) == two_config
    assert hosts.list_episode_host_ids(one.id) == ["h1", "h2"]
    assert hosts.list_episode_host_ids(two.id) == ["h2"]

    edited = EpisodeConfiguration(
        title="Revised technical",
        focus="new focus",
        host_ids=("h2", "h1"),
        research_overrides={"mode": "aggressive"},
        model_overrides={"directing": {"provider": "llama-server", "model": "model-c"}},
    )
    service.edit(one.id, edited)
    assert service.load_configuration(one.id) == edited
    assert service.load_configuration(two.id) == two_config
    assert hosts.list_episode_host_ids(one.id) == ["h2", "h1"]
