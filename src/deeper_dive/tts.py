"""Provider-neutral TTS contract, registry, and deterministic fake provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from deeper_dive.hosts import HostProfile
from deeper_dive.llm import ProviderHealth


@dataclass(frozen=True, slots=True)
class TTSVoice:
    """Normalized voice metadata exposed by every TTS provider."""

    id: str
    name: str
    languages: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TTSRequest:
    """Provider-neutral synthesis request."""

    text: str
    voice: str
    model: str | None = None
    response_format: str = "wav"
    sample_rate_hz: int | None = None


@dataclass(frozen=True, slots=True)
class TTSAudioResult:
    """Normalized synthesized audio and the metadata needed downstream."""

    audio: bytes
    media_type: str
    format: str
    provider: str
    voice: str
    model: str | None = None
    sample_rate_hz: int | None = None
    duration_seconds: float | None = None


class TTSProvider(Protocol):
    """Provider-neutral synthesis interface consumed by orchestration."""

    @property
    def provider_id(self) -> str: ...

    def health(self) -> ProviderHealth: ...

    def voices(self) -> tuple[TTSVoice, ...]: ...

    def synthesize(self, request: TTSRequest) -> TTSAudioResult: ...


class TTSProviderRegistry:
    """Stable provider registry plus per-host provider/voice resolution."""

    def __init__(self) -> None:
        self._providers: dict[str, TTSProvider] = {}

    def register(self, provider: TTSProvider) -> None:
        if not provider.provider_id:
            raise ValueError("provider_id must not be empty")
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> TTSProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"unknown TTS provider: {provider_id}") from exc

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def health(self) -> dict[str, ProviderHealth]:
        return {provider_id: self.get(provider_id).health() for provider_id in self.provider_ids()}

    def voices(self) -> dict[str, tuple[TTSVoice, ...]]:
        return {provider_id: self.get(provider_id).voices() for provider_id in self.provider_ids()}

    def resolve_host(self, host: HostProfile) -> tuple[TTSProvider, TTSVoice]:
        """Resolve and validate the provider/voice assigned to one host."""
        if not host.tts_provider:
            raise ValueError(f"host {host.id!r} has no TTS provider assigned")
        if not host.tts_voice:
            raise ValueError(f"host {host.id!r} has no TTS voice assigned")
        provider = self.get(host.tts_provider)
        voice = next((item for item in provider.voices() if item.id == host.tts_voice), None)
        if voice is None:
            raise ValueError(
                f"unknown TTS voice {host.tts_voice!r} for provider {host.tts_provider!r}"
            )
        return provider, voice


class FakeTTSProvider:
    """Deterministic model-free provider for CI and orchestration tests."""

    def __init__(
        self,
        *,
        provider_id: str = "fake-tts",
        voices: tuple[TTSVoice, ...] | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._voices = voices or (TTSVoice("voice-a", "Voice A", ("en",)),)
        self.requests: list[TTSRequest] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def health(self) -> ProviderHealth:
        return ProviderHealth(True, "ready")

    def voices(self) -> tuple[TTSVoice, ...]:
        return self._voices

    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        self.requests.append(request)
        payload = f"FAKE-AUDIO\n{request.voice}\n{request.text}".encode()
        return TTSAudioResult(
            audio=payload,
            media_type="audio/wav",
            format="wav",
            provider=self.provider_id,
            voice=request.voice,
            model=request.model or "fake-v1",
            sample_rate_hz=request.sample_rate_hz or 24000,
            duration_seconds=max(0.1, len(request.text.split()) / 150 * 60),
        )
