"""Validate finite, positive provider-readiness deadlines before worker allocation."""

from __future__ import annotations

from typing import cast

import pytest

from deeper_dive.guided_async_readiness import FirstRunReadinessCoordinator
from deeper_dive.guided_workflow import WizardContext


@pytest.mark.parametrize(
    "deadline", [0.0, -1.0, float("nan"), float("inf"), -float("inf")]
)
def test_invalid_deadline_rejected_without_starting_a_probe(deadline: float) -> None:
    context = cast(WizardContext, object())
    with pytest.raises(ValueError, match="timeout_seconds must be finite and positive"):
        FirstRunReadinessCoordinator(context, timeout_seconds=deadline)
