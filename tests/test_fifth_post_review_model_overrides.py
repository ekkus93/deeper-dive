"""5PR-03: stored string-form model overrides must not lock an episode."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from test_episode_planner import _service

from deeper_dive.episode_config import EpisodeConfiguration


def _store_raw_overrides(service, episode_id: str, overrides: object) -> None:  # type: ignore[no-untyped-def]
    """Write a row the way an older writer / import would (bypassing normalization)."""

    record = service.repository.get_episode(episode_id)
    payload = json.loads(record.config_json)
    payload["model_overrides"] = overrides
    with service.configurations.database.transaction() as db:
        db.execute(
            "UPDATE episodes SET config_json=? WHERE id=?",
            (json.dumps(payload, sort_keys=True), episode_id),
        )


def test_string_form_override_loads_snapshots_edits_and_plans(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service, episode_id, _ = _service(tmp_path)
    configurations = service.configurations
    _store_raw_overrides(service, episode_id, {"episode_planning": "fake:fake-v1"})

    config = configurations.load_configuration(episode_id)
    snapshot = config.snapshot()
    assert snapshot["model_overrides"] == {
        "episode_planning": {"provider": "fake", "model": "fake-v1"}
    }

    configurations.edit(episode_id, replace(config, title="Renamed"))
    edited = configurations.load_configuration(episode_id)
    assert edited.title == "Renamed"
    assert edited.model_overrides == {"episode_planning": {"provider": "fake", "model": "fake-v1"}}
    assert service.build_plan(episode_id).segments


def test_clearing_a_stored_invalid_override_succeeds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service, episode_id, _ = _service(tmp_path)
    configurations = service.configurations
    _store_raw_overrides(service, episode_id, {"episode_planning": "no-colon-here"})

    config = configurations.load_configuration(episode_id)
    with pytest.raises(ValueError, match="episode_planning"):
        config.snapshot()

    configurations.edit(episode_id, replace(config, model_overrides={}))
    assert configurations.load_configuration(episode_id).model_overrides == {}


@pytest.mark.parametrize("bad", [None, 3, True, ["a"], {"provider": 1}])
def test_unusable_override_shapes_are_still_rejected(bad: object) -> None:
    config = EpisodeConfiguration(title="T", model_overrides={"episode_planning": bad})  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="episode_planning"):
        config.normalized()
