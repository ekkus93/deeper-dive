from __future__ import annotations

import pytest

from deeper_dive.user_errors import actionable_error


@pytest.mark.parametrize(
    ("area", "expected"),
    [
        ("parser", "supported and not damaged"),
        ("provider", "provider health"),
        ("network", "connectivity"),
        ("tts", "selected voice"),
        ("ffmpeg", "FFmpeg is installed"),
    ],
)
def test_common_failures_are_actionable(area: str, expected: str) -> None:
    error = actionable_error(area, RuntimeError("low-level failure"))
    assert expected in error.message
    assert "low-level failure" not in error.message
    assert error.diagnostic == "low-level failure"
