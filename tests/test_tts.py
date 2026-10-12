from __future__ import annotations

import io
import wave

import pytest

from deeper_dive.hosts import HostProfile
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry, TTSRequest, TTSVoice


def test_fake_tts_normalizes_voice_health_and_audio_metadata() -> None:
    provider = FakeTTSProvider()
    assert provider.health().healthy
    assert provider.voices() == (TTSVoice("voice-a", "Voice A", ("en",)),)

    result = provider.synthesize(TTSRequest("hello evidence", "voice-a"))

    assert result.audio.startswith(b"RIFF")
    with wave.open(io.BytesIO(result.audio), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 24000
        assert wav.getnframes() > 0
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


@pytest.mark.parametrize(
    "untrusted_id",
    [
        "https://example.test/v1#access_token=tts-id-canary",
        "Authorization: Bearer tts-id-canary",
    ],
)
def test_registry_unknown_tts_provider_never_echoes_untrusted_id(
    untrusted_id: str,
) -> None:
    registry = TTSProviderRegistry()
    with pytest.raises(KeyError, match="unknown TTS provider") as error:
        registry.get(untrusted_id)

    assert "tts-id-canary" not in str(error.value)
    assert untrusted_id not in str(error.value)
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("missing_field", ["provider", "voice"])
def test_host_missing_tts_assignment_does_not_echo_host_id(
    missing_field: str,
) -> None:
    registry = TTSProviderRegistry()
    host_id = "https://example.test/v1#token=host-id-canary"
    host = HostProfile(
        host_id, "project", "Test host",
        tts_provider="fake-tts" if missing_field == "voice" else None,
    )
    with pytest.raises(ValueError, match=f"no TTS {missing_field}") as error:
        registry.resolve_host(host)
    assert "host-id-canary" not in str(error.value)


def test_unknown_host_voice_never_echoes_credential_like_voice_id() -> None:
    registry = TTSProviderRegistry()
    registry.register(FakeTTSProvider())
    voice_id = "https://example.test/v1#api_key=voice-id-canary"
    host = HostProfile(
        "host-1", "project", "Test host",
        tts_provider="fake-tts", tts_voice=voice_id,
    )
    with pytest.raises(ValueError, match="unknown TTS voice") as error:
        registry.resolve_host(host)
    assert "voice-id-canary" not in str(error.value)
    assert voice_id not in str(error.value)
