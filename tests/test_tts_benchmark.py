from __future__ import annotations

import pytest

from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tts_benchmark import BENCHMARK_TEXT, TTSBenchmarkService, benchmark_math


def test_benchmark_math_is_independent_of_real_model() -> None:
    rtf, speed, estimate20, estimate30 = benchmark_math(5.0, 20.0)
    assert rtf == pytest.approx(0.25)
    assert speed == pytest.approx(4.0)
    assert estimate20 == pytest.approx(300.0)
    assert estimate30 == pytest.approx(450.0)


def test_benchmark_math_rejects_nonpositive_durations() -> None:
    with pytest.raises(ValueError):
        benchmark_math(0.0, 10.0)
    with pytest.raises(ValueError):
        benchmark_math(1.0, 0.0)


def test_benchmark_synthesizes_deterministic_passage_and_records_metadata() -> None:
    ticks = iter((100.0, 102.0))
    provider = FakeTTSProvider()
    result = TTSBenchmarkService(clock=lambda: next(ticks)).run(
        provider, voice="voice-a", model="fake-v1"
    )

    assert provider.requests[0].text == BENCHMARK_TEXT
    assert result.wall_seconds == pytest.approx(2.0)
    assert result.audio_seconds > 0
    assert result.realtime_factor == pytest.approx(2.0 / result.audio_seconds)
    assert result.x_realtime == pytest.approx(result.audio_seconds / 2.0)
    assert result.estimated_20_minute_render_seconds == pytest.approx(
        1200 * result.realtime_factor
    )
    assert result.estimated_30_minute_render_seconds == pytest.approx(
        1800 * result.realtime_factor
    )
    assert result.provider == "fake-tts"
    assert result.model == "fake-v1"
    assert result.voice == "voice-a"
    assert result.cpu
    assert result.runtime.startswith("Python ")
