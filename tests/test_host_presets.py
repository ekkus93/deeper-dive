from __future__ import annotations

import json

import pytest

from deeper_dive.hosts import PRESET_DEFINITIONS, create_host_from_preset, preset_names

EXPECTED = (
    "curious_explainer",
    "skeptic",
    "synthesizer",
    "domain_expert",
    "practitioner",
    "historian",
    "moderator",
    "custom",
)


def test_all_required_presets_create_normal_serializable_profiles() -> None:
    assert preset_names() == EXPECTED
    for preset in EXPECTED:
        host = create_host_from_preset(preset, "project-1", host_id=f"host-{preset}")
        record = host.to_record()
        assert record.project_id == "project-1"
        assert record.preset_origin == preset
        assert json.loads(record.behavior_json) == host.behavior
        assert json.loads(record.evidence_priorities_json) == host.evidence_priorities


def test_preset_profiles_are_independent_editable_starting_points() -> None:
    first = create_host_from_preset("skeptic", "project-1")
    second = create_host_from_preset("skeptic", "project-1")
    first.display_name = "Edited skeptic"
    first.behavior["skepticism"] = 0.1
    first.evidence_priorities.append("new priority")

    assert second.display_name == "Skeptic"
    assert second.behavior["skepticism"] == 0.95
    assert "new priority" not in second.evidence_priorities
    assert PRESET_DEFINITIONS["skeptic"]["display_name"] == "Skeptic"


def test_unknown_preset_is_rejected() -> None:
    with pytest.raises(KeyError):
        create_host_from_preset("unknown", "project-1")
