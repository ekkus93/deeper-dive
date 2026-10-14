"""TPR-19.2: Quick Deep Dive research overrides never echo a rejected value."""

from __future__ import annotations

import pytest

from deeper_dive.quick_deep_dive import QuickDeepDiveDefaults, QuickDeepDiveService
from deeper_dive.research_policy import ResearchMode


@pytest.mark.parametrize("key", ["quick_deep_dive_research_policy", "research_policy"])
def test_rejected_research_override_is_not_echoed(key: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        QuickDeepDiveService._apply_overrides(QuickDeepDiveDefaults(), {key: "sk-CANARY-VALUE"})
    assert "sk-CANARY-VALUE" not in str(excinfo.value)
    assert "CANARY" not in repr(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__


@pytest.mark.parametrize("raw", ["Useful", " USEFUL ", "useful"])
def test_research_override_is_case_and_whitespace_insensitive_like_settings(raw: str) -> None:
    result = QuickDeepDiveService._apply_overrides(
        QuickDeepDiveDefaults(), {"quick_deep_dive_research_policy": raw}
    )
    assert result.research_mode is ResearchMode.USEFUL
