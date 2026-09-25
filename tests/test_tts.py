from __future__ import annotations

import pytest

from deeper_dive.hosts import HostProfile
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry, TTSRequest, TTSVoice


def test_fake_tts_normalizes_voice_health_and_audio_metadata() -> None:
    provider = FakeTTSProvider()
    assert provider.health().healthy
    assert provider.voices() == (TTSVoice("voice-a", "Voice A", ("en",)),)

    result = provider.synthesize(TTSRequest("hello evidence", "voice-a"))

    assert result.audio.startswith(b"FAKE-WAV")
    assert result.media_type == "audio/wav"
    assert result.format == "wav"
    assert result.provider == "fake-tts"
    assert result.voice == "voice-a"
    assert result.model == "fake-v1"
    assert result.sample_rate_hz == 24000
    assert result.duration_seconds is not None and result.duration_seconds > 0


def test_registry_resolves_different_providers_and_voices_per_host() -> None:
    registry = TTSProviderRegistry()
    registry.register(FakeTTSProvider(provider_id="local", voices=(TTSVoice("calm", "Calm"),)))
    registry.register(FakeTTSProvider(provider_id="cloud", voices=(TTSVoice("bright", "Bright"),)))
    local = HostProfile("h1", "p1", "Local", tts_provider="local", tts_voice="calm")
    cloud = HostProfile("h2", "p1", "Cloud", tts_provider="cloud", tts_voice="bright")

    local_provider, local_voice = registry.resolve_host(local)
    cloud_provider, cloud_voice = registry.resolve_host(cloud)

    assert (local_provider.provider_id, local_voice.id) == ("local", "calm")
    assert (cloud_provider.provider_id, cloud_voice.id) == ("cloud", "bright")


def test_registry_rejects_missing_or_unknown_host_assignments() -> None:
    registry = TTSProviderRegistry()
    registry.register(FakeTTSProvider())

    with pytest.raises(ValueError, match="no TTS provider"):
        registry.resolve_host(HostProfile("h1", "p1", "Missing"))
    with pytest.raises(KeyError, match="unknown TTS provider"):
        registry.resolve_host(
            HostProfile("h2", "p1", "Unknown", tts_provider="nope", tts_voice="voice-a")
        )
    with pytest.raises(ValueError, match="unknown TTS voice"):
        registry.resolve_host(
            HostProfile("h3", "p1", "Unknown voice", tts_provider="fake-tts", tts_voice="nope")
        )
