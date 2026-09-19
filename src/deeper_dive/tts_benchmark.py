"""Deterministic TTS runtime benchmarking and render-time estimates."""

from __future__ import annotations

import os
import platform
import time
from dataclasses import dataclass
from typing import Callable

from deeper_dive.tts import TTSProvider, TTSRequest

BENCHMARK_TEXT = (
    "Deeper Dive turns source material into a grounded conversation. "
    "This deterministic passage measures local speech synthesis performance "
    "without changing between benchmark runs."
)


@dataclass(frozen=True, slots=True)
class TTSBenchmarkResult:
    wall_seconds: float
    audio_seconds: float
    realtime_factor: float
    x_realtime: float
    estimated_20_minute_render_seconds: float
    estimated_30_minute_render_seconds: float
    provider: str
    model: str | None
    voice: str
    cpu: str
    runtime: str


def benchmark_math(wall_seconds: float, audio_seconds: float) -> tuple[float, float, float, float]:
    """Return RTF, x-realtime, and 20/30 minute render estimates."""
    if wall_seconds <= 0 or audio_seconds <= 0:
        raise ValueError("wall and audio durations must be positive")
    realtime_factor = wall_seconds / audio_seconds
    x_realtime = audio_seconds / wall_seconds
    return (
        realtime_factor,
        x_realtime,
        20 * 60 * realtime_factor,
        30 * 60 * realtime_factor,
    )


class TTSBenchmarkService:
    def __init__(self, *, clock: Callable[[], float] = time.perf_counter) -> None:
        self.clock = clock

    def run(
        self,
        provider: TTSProvider,
        *,
        voice: str,
        model: str | None = None,
        text: str = BENCHMARK_TEXT,
    ) -> TTSBenchmarkResult:
        started = self.clock()
        audio = provider.synthesize(TTSRequest(text=text, voice=voice, model=model))
        wall_seconds = self.clock() - started
        if audio.duration_seconds is None or audio.duration_seconds <= 0:
            raise ValueError("TTS provider must report positive audio duration for benchmarking")
        rtf, speed, estimate20, estimate30 = benchmark_math(wall_seconds, audio.duration_seconds)
        return TTSBenchmarkResult(
            wall_seconds=wall_seconds,
            audio_seconds=audio.duration_seconds,
            realtime_factor=rtf,
            x_realtime=speed,
            estimated_20_minute_render_seconds=estimate20,
            estimated_30_minute_render_seconds=estimate30,
            provider=provider.provider_id,
            model=audio.model or model,
            voice=audio.voice,
            cpu=platform.processor() or platform.machine() or "unknown",
            runtime=f"Python {platform.python_version()} ({os.name})",
        )
