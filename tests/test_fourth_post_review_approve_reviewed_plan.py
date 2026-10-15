"""FPR-07: approval applies to the plan the user reviewed, not whatever is stored."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_third_post_review_plan_approval import _setup

from deeper_dive.episode_config import EpisodeConfigurationConflict
from deeper_dive.storage.episode_repositories import HostEpisodeRepository


def test_approving_a_replaced_plan_is_refused_and_the_new_plan_stays_draft(
    tmp_path: Path,
) -> None:
    _configurations, planner, database, episode_id = _setup(tmp_path)
    reviewed = planner.load_plan(episode_id)

    # Another surface regenerates the plan under the same configuration.
    replacement = planner.regenerate_plan(episode_id)
    assert replacement.id != reviewed.id

    with pytest.raises(EpisodeConfigurationConflict, match="reviewed"):
        planner.approve_plan(episode_id, reviewed_plan_id=reviewed.id)

    stored = HostEpisodeRepository(database).get_plan(episode_id)
    assert stored is not None
    assert stored.id == replacement.id
    assert stored.status == "draft"


def test_approving_the_reviewed_plan_still_works_and_is_idempotent(tmp_path: Path) -> None:
    _configurations, planner, database, episode_id = _setup(tmp_path)
    reviewed = planner.load_plan(episode_id)

    assert planner.approve_plan(episode_id, reviewed_plan_id=reviewed.id).id == reviewed.id
    # Re-approving the same already-approved plan is a harmless no-op success.
    assert planner.approve_plan(episode_id, reviewed_plan_id=reviewed.id).id == reviewed.id
    stored = HostEpisodeRepository(database).get_plan(episode_id)
    assert stored is not None and stored.status == "approved"


def test_approval_without_a_reviewed_id_keeps_the_old_behaviour(tmp_path: Path) -> None:
    _configurations, planner, _database, episode_id = _setup(tmp_path)
    assert planner.approve_plan(episode_id).id == planner.load_plan(episode_id).id
