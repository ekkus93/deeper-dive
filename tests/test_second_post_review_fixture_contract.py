"""Assert the shared second-review fixture exercises real production boundaries."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.research_policy import ResearchMode, ResearchPolicyStore
from deeper_dive.storage.database import Database
from deeper_dive.user_config import UserConfigStore


def test_two_project_fixture_contains_indexed_corpora_and_generation_artifacts(
    second_post_review_acceptance: Callable[[], Any],
) -> None:
    fixture = second_post_review_acceptance()
    service = fixture.completed.first.service
    data_dir = service.workspaces.data_dir
    config = UserConfigStore(data_dir / "config.json").load()
    assert config.providers["fake"].provider_type == "fake"
    assert config.providers["speech"].provider_type == "fake-tts"
    assert config.defaults["research_policy"] == "useful"
    assert (data_dir / "config.json").read_bytes() == fixture.config_bytes
    assert len(set(fixture.identity_snapshot)) == len(fixture.identity_snapshot)

    episodes = (fixture.completed.first, fixture.completed.second)
    for current in episodes:
        sources = service.list_sources(current.project_id)
        assert len(sources) == 1
        chunks = service.list_source_chunks(current.project_id, sources[0].id)
        assert chunks and all(chunk.text for chunk in chunks)
        host_ids = service.hosts(current.project_id).list_episode_host_ids(current.episode_id)
        assert len(host_ids) == 2
        policy = ResearchPolicyStore(
            Database(service.workspaces.project_root(current.project_id) / "project.db")
        )
        assert policy.episode(current.project_id, current.episode_id).mode is ResearchMode.USEFUL
        run = service.runs(current.project_id).get(current.run_id)
        assert run is not None and run.state == "completed"
        assert current.turn_ids and len(set(current.turn_ids)) == len(current.turn_ids)
        assert current.transcript_path.read_bytes()
        assert current.audio_path.read_bytes()

    foreign_source_id = service.list_sources(episodes[1].project_id)[0].id
    assert service.get_source(episodes[0].project_id, foreign_source_id) is None

    pending_run = service.runs(fixture.pending_project_id).get(fixture.pending_run_id)
    assert pending_run is not None and pending_run.state == "pending"
    configuration = EpisodeConfigurationService(
        Database(service.workspaces.project_root(fixture.pending_project_id) / "project.db")
    ).load_configuration(fixture.pending_episode_id)
    serialized = json.dumps(
        configuration.snapshot(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert serialized == fixture.pending_config_snapshot
