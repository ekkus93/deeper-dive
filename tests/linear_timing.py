"""Compare growth, not wall-clock: quadratic behaviour shows as ~16x for 4x the input."""

from __future__ import annotations

import time
from collections.abc import Callable


def _best_of(function: Callable[[str], object], text: str, repeats: int = 2) -> float:
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        function(text)
        best = min(best, time.perf_counter() - start)
    return best


def assert_scales_linearly(
    function: Callable[[str], object],
    make_text: Callable[[int], str],
    *,
    large: int,
    label: str = "",
) -> None:
    """``function`` on ``large`` characters must cost well under quadratic growth.

    4x the input may cost up to 8x the time (linear is 4x; quadratic is 16x), plus a
    fixed allowance so a very fast small run cannot make the ratio meaningless.
    """

    small_time = _best_of(function, make_text(large // 4))
    large_time = _best_of(function, make_text(large))
    assert large_time <= max(8 * small_time, 0.5) + 1.0, (
        f"{label}: {small_time:.3f}s at {large // 4} chars, {large_time:.3f}s at {large}"
    )
