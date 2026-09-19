"""Optional CPU-only KittenTTS Micro provider integration."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import struct
import wave
from collections.abc import Callable, Iterable
from typing import Protocol

from deeper_dive.llm import ProviderHealth
from deeper_dive.tts import TTSAudioResult, TTSRequest, TTSVoice

MICRO_MODEL_ID = "KittenML/kitten-tts-micro-0.8"
SAMPLE_RATE_HZ = 24_000
VOICE_NAMES = ("Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo")


class KittenRuntime(Protocol):
    """Narrow seam around the developer-preview KittenTTS runtime."""

    available_voices: Iterable[str]

    def generate(self, text: str, *, voice: str, speed: float = 1.0) -> Iterable[float]: ...


RuntimeFactory = Callable[[str], KittenRuntime]


def _default_runtime_factory(model_id: str) -> KittenRuntime:
    try:
        from kittentts import KittenTTS  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "KittenTTS runtime is not installed; install the optional KittenTTS runtime first"
        ) from exc
    return KittenTTS(model_id)  # type: ignore[no-any-return]


def _wav_bytes(samples: Iterable[float], sample_rate_hz: int = SAMPLE_RATE_HZ) -> bytes:
    """Encode Kitten's normalized mono float samples as 16-bit PCM WAV."""
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate_hz)
        frames = bytearray()
        for sample in samples:
            bounded = max(-1.0, min(1.0, float(sample)))
            frames.extend(struct.pack("<h", round(bounded * 32767)))
        wav.writeframes(bytes(frames))
    return output.getvalue()


class KittenTTSMicroProvider:
    """Lazy, CPU-only KittenTTS Micro adapter.

    Construction and health checks never download a model. The actual developer-preview
    runtime is imported and initialized only on first synthesis. Model installation and
    explicit download lifecycle are owned by DD-122.
    """

    def __init__(self, *, runtime_factory: RuntimeFactory | None = None) -> None:
        self._runtime_factory = runtime_factory or _default_runtime_factory
        self._runtime: KittenRuntime | None = None

    @property
    def provider_id(self) -> str:
        return "kitten"

    def health(self) -> ProviderHealth:
        if self._runtime is not None:
            return ProviderHealth(True, "KittenTTS Micro runtime loaded on CPU")
        if self._runtime_factory is not _default_runtime_factory:
            return ProviderHealth(True, "KittenTTS runtime available")
        if importlib.util.find_spec("kittentts") is None:
            return ProviderHealth(False, "KittenTTS runtime is not installed")
        return ProviderHealth(True, "KittenTTS runtime installed; model loads on first synthesis")

    def voices(self) -> tuple[TTSVoice, ...]:
        names = tuple(self._runtime.available_voices) if self._runtime is not None else VOICE_NAMES
        return tuple(TTSVoice(name, name, ("en",), {"model": MICRO_MODEL_ID}) for name in names)

    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        if request.response_format.lower() != "wav":
            raise ValueError("KittenTTS Micro provider currently emits WAV only")
        if request.sample_rate_hz not in (None, SAMPLE_RATE_HZ):
            raise ValueError("KittenTTS Micro emits 24000 Hz audio; resampling belongs to DD-130")
        if request.voice not in {voice.id for voice in self.voices()}:
            raise ValueError(f"unknown KittenTTS voice: {request.voice}")
        runtime = self._load_runtime()
        try:
            samples = tuple(runtime.generate(request.text, voice=request.voice, speed=1.0))
        except Exception as exc:
            raise RuntimeError(f"KittenTTS synthesis failed: {exc}") from exc
        if not samples:
            raise RuntimeError("KittenTTS synthesis returned empty audio")
        audio = _wav_bytes(samples)
        duration = len(samples) / SAMPLE_RATE_HZ
        return TTSAudioResult(
            audio=audio,
            media_type="audio/wav",
            format="wav",
            provider=self.provider_id,
            voice=request.voice,
            model=MICRO_MODEL_ID,
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_seconds=duration,
        )

    async def synthesize_async(self, request: TTSRequest) -> TTSAudioResult:
        """Run blocking inference off-loop and do not report cancellation before it stops."""
        task = asyncio.create_task(asyncio.to_thread(self.synthesize, request))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Kitten/ONNX inference is not cooperatively cancellable. Wait for the worker
            # to finish before propagating cancellation so callers cannot claim it stopped early.
            await task
            raise

    def _load_runtime(self) -> KittenRuntime:
        if self._runtime is None:
            try:
                self._runtime = self._runtime_factory(MICRO_MODEL_ID)
            except Exception as exc:
                raise RuntimeError(f"KittenTTS Micro model/runtime unavailable: {exc}") from exc
        return self._runtime
