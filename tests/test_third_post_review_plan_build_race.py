"""TPR-12: build_plan reads configuration and revision from one snapshot."""

from __future__ import annotations

import pytest
from test_episode_planner import _service

from deeper_dive.episode_config import EpisodeConfiguration
from deeper_dive.storage.episode_repositories import HostEpisodeRepository


def test_edit_after_the_snapshot_read_cannot_store_a_stale_plan(tmp_path, monkeypatch) -> None:
    service, episode_id, _ = _service(tmp_path)
    reads = {"count": 0}
    real_get = HostEpisodeRepository.get_episode

    def get_then_edit(self, requested_id):
        record = real_get(self, requested_id)
        reads["count"] += 1
        if reads["count"] == 1:
            # An edit lands immediately after the first (and only) episode read.
            service.configurations.edit(
                requested_id,
                EpisodeConfiguration(
                    title="Edited concurrently",
                    focus="",
                    target_duration_seconds=900,
                    host_ids=("h1", "h2"),
                ),
            )
        return record

    monkeypatch.setattr(HostEpisodeRepository, "get_episode", get_then_edit)
    with pytest.raises(ValueError, match="changed while the plan was being built"):
        service.build_plan(episode_id)
    monkeypatch.setattr(HostEpisodeRepository, "get_episode", real_get)
    with service.database.connection() as db:
        stored = db.execute(
            "SELECT COUNT(*) FROM episode_plans WHERE episode_id=?", (episode_id,)
        ).fetchone()[0]
    assert stored == 0


def _edit_after_first_episode_read(service, monkeypatch, episode_id):  # type: ignore[no-untyped-def]
    reads = {"count": 0}
    real_get = HostEpisodeRepository.get_episode

    def get_then_edit(self, requested_id):  # type: ignore[no-untyped-def]
        record = real_get(self, requested_id)
        reads["count"] += 1
        if reads["count"] == 1:
            service.configurations.edit(
                requested_id,
                EpisodeConfiguration(
                    title="Edited concurrently",
                    focus="",
                    target_duration_seconds=900,
                    host_ids=("h1", "h2"),
                ),
            )
        return record

    monkeypatch.setattr(HostEpisodeRepository, "get_episode", get_then_edit)
    return real_get


def test_segment_regeneration_cannot_store_a_plan_for_stale_inputs(tmp_path, monkeypatch) -> None:
    service, episode_id, _ = _service(tmp_path)
    service.build_plan(episode_id)
    real_get = _edit_after_first_episode_read(service, monkeypatch, episode_id)
    with pytest.raises(ValueError):
        service.regenerate_segment(episode_id, 1)
    monkeypatch.setattr(HostEpisodeRepository, "get_episode", real_get)
    with service.database.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM episode_plans").fetchone()[0] == 0


def test_segment_edit_cannot_store_a_plan_for_stale_inputs(tmp_path, monkeypatch) -> None:
    from deeper_dive.episode_planner import PlannedSegment

    service, episode_id, _ = _service(tmp_path)
    service.build_plan(episode_id)
    real_get = _edit_after_first_episode_read(service, monkeypatch, episode_id)
    with pytest.raises(ValueError):
        service.edit_segment(episode_id, 0, PlannedSegment("Changed", "p", 100))
    monkeypatch.setattr(HostEpisodeRepository, "get_episode", real_get)
    with service.database.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM episode_plans").fetchone()[0] == 0
