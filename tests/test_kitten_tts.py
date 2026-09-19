from __future__ import annotations

import asyncio
import threading
import time
import wave
from io import BytesIO

import pytest

from deeper_dive.kitten_tts import MICRO_MODEL_ID, KittenTTSMicroProvider
from deeper_dive.tts import TTSRequest


class _FakeRuntime:
    available_voices = ("Jasper", "Luna")

    def __init__(self, *, gate: threading.Event | None = None) -> None:
        self.gate = gate
        self.calls: list[tuple[str, str, float]] = []

    def generate(self, text: str, *, voice: str, speed: float = 1.0) -> tuple[float, ...]:
        self.calls.append((text, voice, speed))
        if self.gate is not None:
            self.gate.wait(timeout=2)
        return (0.0, 0.25, -0.25, 1.0, -1.0)


def test_kitten_micro_is_cpu_lazy_lists_voices_and_emits_wav() -> None:
    created: list[str] = []
    runtime = _FakeRuntime()

    def factory(model_id: str) -> _FakeRuntime:
        created.append(model_id)
        return runtime

    provider = KittenTTSMicroProvider(runtime_factory=factory)
    assert provider.health().healthy
    assert created == []
    assert [voice.id for voice in provider.voices()] == [
        "Bella",
        "Jasper",
        "Luna",
        "Bruno",
        "Rosie",
        "Hugo",
        "Kiki",
        "Leo",
    ]

    result = provider.synthesize(TTSRequest("hello", "Jasper"))

    assert created == [MICRO_MODEL_ID]
    assert runtime.calls == [("hello", "Jasper", 1.0)]
    assert result.provider == "kitten"
    assert result.model == MICRO_MODEL_ID
    assert result.sample_rate_hz == 24_000
    with wave.open(BytesIO(result.audio), "rb") as wav:
        assert wav.getframerate() == 24_000
        assert wav.getnchannels() == 1
        assert wav.getnframes() == 5


def test_kitten_micro_handles_runtime_or_model_absence_cleanly() -> None:
    def unavailable(_model_id: str) -> _FakeRuntime:
        raise FileNotFoundError("model missing")

    provider = KittenTTSMicroProvider(runtime_factory=unavailable)
    with pytest.raises(RuntimeError, match="model/runtime unavailable.*model missing"):
        provider.synthesize(TTSRequest("hello", "Jasper"))


def test_kitten_micro_rejects_unsupported_output_contract() -> None:
    provider = KittenTTSMicroProvider(runtime_factory=lambda _model: _FakeRuntime())
    with pytest.raises(ValueError, match="WAV only"):
        provider.synthesize(TTSRequest("hello", "Jasper", response_format="mp3"))
    with pytest.raises(ValueError, match="24000 Hz"):
        provider.synthesize(TTSRequest("hello", "Jasper", sample_rate_hz=16_000))


def test_async_synthesis_runs_off_event_loop() -> None:
    gate = threading.Event()
    runtime = _FakeRuntime(gate=gate)
    provider = KittenTTSMicroProvider(runtime_factory=lambda _model: runtime)

    async def exercise() -> None:
        task = asyncio.create_task(provider.synthesize_async(TTSRequest("hello", "Jasper")))
        await asyncio.sleep(0.01)
        # The loop remains responsive while the worker is blocked.
        assert not task.done()
        gate.set()
        result = await task
        assert result.audio

    asyncio.run(exercise())


def test_async_cancellation_is_truthful_for_uninterruptible_inference() -> None:
    gate = threading.Event()
    runtime = _FakeRuntime(gate=gate)
    provider = KittenTTSMicroProvider(runtime_factory=lambda _model: runtime)

    async def exercise() -> None:
        task = asyncio.create_task(provider.synthesize_async(TTSRequest("hello", "Jasper")))
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
