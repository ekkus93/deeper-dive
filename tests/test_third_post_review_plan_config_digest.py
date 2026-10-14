"""TPR-04: a plan records the configuration it was built from; validity rejects stale inputs."""

from __future__ import annotations

import json
from dataclasses import replace

from test_episode_planner import _service

from deeper_dive.plan_validity import PLAN_CONFIG_DIGEST_KEY, evaluate_episode_plan


def test_fresh_plan_is_usable_and_records_a_digest(tmp_path) -> None:
    service, episode_id, _ = _service(tmp_path)
    service.build_plan(episode_id)
    record = service.repository.get_plan(episode_id)
    assert PLAN_CONFIG_DIGEST_KEY in json.loads(record.plan_json)
    assert evaluate_episode_plan(service.database, episode_id).usable


def test_plan_built_from_other_inputs_is_not_usable(tmp_path) -> None:
    service, episode_id, _ = _service(tmp_path)
    service.build_plan(episode_id)
    # A configuration change that bypassed the normal plan invalidation.
    with service.database.transaction() as db:
        db.execute(
            "UPDATE episodes SET config_json=? WHERE id=?",
            ('{"duration_only_edit": 1}', episode_id),
        )
    validity = evaluate_episode_plan(service.database, episode_id)
    assert not validity.usable
    assert any("different episode configuration" in issue for issue in validity.issues)


def test_legacy_plan_without_a_digest_stays_usable(tmp_path) -> None:
    service, episode_id, _ = _service(tmp_path)
    service.build_plan(episode_id)
    record = service.repository.get_plan(episode_id)
    legacy = {k: v for k, v in json.loads(record.plan_json).items() if k != PLAN_CONFIG_DIGEST_KEY}
    with service.database.transaction() as db:
        db.execute(
            "UPDATE episode_plans SET plan_json=? WHERE id=?", (json.dumps(legacy), record.id)
        )
    assert evaluate_episode_plan(service.database, episode_id).usable


def test_duration_only_edit_removes_the_old_plan(tmp_path) -> None:
    service, episode_id, _ = _service(tmp_path)
    service.build_plan(episode_id)
    current = service.configurations.load_configuration(episode_id)
    service.configurations.edit(
        episode_id, replace(current, target_duration_seconds=current.target_duration_seconds + 60)
    )
    validity = evaluate_episode_plan(service.database, episode_id)
    assert not validity.usable
