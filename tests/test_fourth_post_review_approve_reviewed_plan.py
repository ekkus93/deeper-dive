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


def test_revision_cas_alone_rejects_approval_when_the_plan_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FPR-18: the TPR-04 race test deleted the plan; here the plan row survives.

    The configuration revision changes through raw SQL (so no plan invalidation runs),
    which means only the episode-revision compare-and-swap can reject the approval.
    """

    _configurations, planner, database, episode_id = _setup(tmp_path)
    original_load = planner.load_plan

    def load_then_bump_revision(eid: str):  # type: ignore[no-untyped-def]
        plan = original_load(eid)
        with database.transaction() as db:
            db.execute("UPDATE episodes SET config_json=? WHERE id=?", ('{"bumped": true}', eid))
        return plan

    monkeypatch.setattr(planner, "load_plan", load_then_bump_revision)
    with pytest.raises(EpisodeConfigurationConflict, match="changed while"):
        planner.approve_plan(episode_id)

    stored = HostEpisodeRepository(database).get_plan(episode_id)
    assert stored is not None and stored.status == "draft"
