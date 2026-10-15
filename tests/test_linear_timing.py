from __future__ import annotations

import pytest
from linear_timing import assert_scales_linearly


def test_linear_timing_helper_rejects_quadratic_work() -> None:
    def quadratic(text: str) -> int:
        return sum(1 for _left in text for _right in text)

    with pytest.raises(AssertionError, match="quadratic self-test"):
        assert_scales_linearly(
            quadratic, lambda size: "x" * size, large=2048, label="quadratic self-test"
        )
