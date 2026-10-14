"""TPR-10: every dirty-form transition kind has explicit, distinct wording."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from deeper_dive.wizard_shell import describe_transition, transition_kinds

SRC = Path(__file__).resolve().parents[1] / "src" / "deeper_dive"


def _requested_kinds() -> set[str]:
    """Kinds passed to ``_request_dirty_transition`` anywhere in production code."""

    kinds: set[str] = set()
    pattern = re.compile(r"_request_dirty_transition\(\s*f?\"([a-z-]+)[\":]")
    for path in SRC.glob("*.py"):
        kinds.update(pattern.findall(path.read_text()))
    return kinds


def test_scan_finds_the_known_call_sites() -> None:
    kinds = _requested_kinds()
    assert {"back", "continue", "exit", "host-select", "plan-select", "create-host"} <= kinds


@pytest.mark.parametrize("kind", sorted(_requested_kinds() | {"navigate"}))
def test_every_requested_kind_has_a_label(kind: str) -> None:
    assert kind in transition_kinds()
    labels = describe_transition(f"{kind}:argument")
    fallback = describe_transition("definitely-unknown")
    assert labels != fallback
    assert labels.save != labels.discard


@pytest.mark.parametrize(
    ("transition", "fragment"),
    [
        ("host-select:h2", "host"),
        ("plan-select:p2", "plan"),
        ("create-recommended-hosts", "recommended hosts"),
    ],
)
def test_previously_unlabelled_kinds_name_their_action(transition: str, fragment: str) -> None:
    labels = describe_transition(transition)
    assert fragment in labels.action
    assert (
        fragment in labels.save.lower()
        or "host" in labels.save.lower()
        or "plan" in labels.save.lower()
    )
    assert labels.save != "Save changes and leave"
