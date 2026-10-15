"""TPR-10: every dirty-form transition is a typed value with distinct wording."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from deeper_dive.wizard_transitions import (
    Transition,
    TransitionKind,
    describe_transition,
    transition_kinds,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "deeper_dive"


def test_every_kind_is_labelled_with_distinct_save_and_discard_wording() -> None:
    assert transition_kinds() == set(TransitionKind)
    for kind in TransitionKind:
        labels = describe_transition(Transition(kind, "argument"))
        assert labels.action
        assert labels.save != labels.discard, kind


def test_labels_are_distinct_per_kind() -> None:
    actions = [
        describe_transition(Transition(kind, "x")).action
        for kind in TransitionKind
        if kind is not TransitionKind.NAVIGATE
    ]
    assert len(actions) == len(set(actions))


def test_production_never_requests_a_transition_from_a_string() -> None:
    """Call sites must pass ``Transition`` values, not encoded strings."""

    pattern = re.compile(r"_request_dirty_transition\(\s*f?[\"']")
    offenders = [p.name for p in SRC.glob("*.py") if pattern.search(p.read_text())]
    assert offenders == []


def test_encoding_round_trips_for_display() -> None:
    assert Transition(TransitionKind.BACK).encoded == "back"
    assert Transition(TransitionKind.HOST_SELECT, "h2").encoded == "host-select:h2"
    assert str(Transition(TransitionKind.NAVIGATE, "home")) == "navigate:home"


@pytest.mark.parametrize(
    ("transition", "fragment"),
    [
        (Transition(TransitionKind.HOST_SELECT, "h2"), "host"),
        (Transition(TransitionKind.PLAN_SELECT, "2"), "plan"),
        (Transition(TransitionKind.CREATE_RECOMMENDED_HOSTS), "recommended hosts"),
    ],
)
def test_previously_unlabelled_kinds_name_their_action(
    transition: Transition, fragment: str
) -> None:
    labels = describe_transition(transition)
    assert fragment in labels.action
    assert labels.save != "Save changes and leave"


def test_navigate_wording_uses_the_destination() -> None:
    labels = describe_transition(Transition(TransitionKind.NAVIGATE, "new-deep-dive"))
    assert labels.action == "go to new deep dive"
    assert labels.save == "Save changes and go to New Deep Dive"
