"""FPR-14: segment operations never persist a stale plan under a newer configuration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from test_third_post_review_plan_approval import _setup

from deeper_dive.episode_config import EpisodeConfigurationConflict
from deeper_dive.episode_planner import PlannedSegment
from deeper_dive.storage.episode_repositories import HostEpisodeRepository


def _edit_config(configurations: Any, episode_id: str) -> None:
    configurations.edit(
        episode_id,
        replace(configurations.load_configuration(episode_id), target_duration_seconds=1200),
    )


@pytest.mark.parametrize("operation", ["regenerate_segment", "edit_segment"])
def test_edit_between_plan_load_and_snapshot_is_a_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    configurations, planner, database, episode_id = _setup(tmp_path)
    original_load = planner.load_plan

    def load_then_edit(eid: str) -> Any:
        plan = original_load(eid)
        _edit_config(configurations, eid)  # deterministic race window
        return plan

    monkeypatch.setattr(planner, "load_plan", load_then_edit)
    segment = PlannedSegment("Edited", "p", 600, (), (), ("h1",))
    with pytest.raises(EpisodeConfigurationConflict):
        if operation == "edit_segment":
            planner.edit_segment(episode_id, 0, segment)
        else:
            planner.regenerate_segment(episode_id, 0)

    # Nothing stale was stored: the edit removed the plan and no operation re-added it.
    assert HostEpisodeRepository(database).get_plan(episode_id) is None


@pytest.mark.parametrize("operation", ["regenerate_segment", "edit_segment"])
def test_operations_still_work_without_a_race(tmp_path: Path, operation: str) -> None:
    _configurations, planner, _database, episode_id = _setup(tmp_path)
    segment = PlannedSegment("Edited", "p", 600, (), (), ("h1",))
    plan = (
        planner.edit_segment(episode_id, 0, segment)
        if operation == "edit_segment"
        else planner.regenerate_segment(episode_id, 0)
    )
    assert len(plan.segments) == 1
