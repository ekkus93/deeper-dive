from __future__ import annotations

import pytest

from deeper_dive.elevenlabs_tts import (
    ElevenLabsAuthError,
    ElevenLabsTTSError,
    ElevenLabsTTSProvider,
)
from deeper_dive.tts import TTSRequest


def test_elevenlabs_lists_normalized_voices() -> None:
    def get_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, object]:
        assert url.endswith("/voices")
        assert headers == {"xi-api-key": "key"}
        return {
            "voices": [
                {"voice_id": "v1", "name": "Alice", "category": "premade"},
                {"voice_id": "v2", "name": "Bob"},
            ]
        }

    provider = ElevenLabsTTSProvider(api_key="key", request_json=get_json)
    voices = provider.voices()
    assert [(voice.id, voice.name) for voice in voices] == [("v1", "Alice"), ("v2", "Bob")]
    assert voices[0].metadata == {"category": "premade"}


def test_elevenlabs_synthesizes_and_normalizes_audio() -> None:
    seen: dict[str, object] = {}

    def binary(
        url: str, payload: dict[str, object], headers: dict[str, str], timeout: float
    ) -> bytes:
        seen.update({"url": url, "payload": payload, "headers": headers})
        return b"mp3-audio"

    provider = ElevenLabsTTSProvider(api_key="key", request_binary=binary)
    result = provider.synthesize(TTSRequest("Hello", "voice/id", model="custom-model"))

    assert result.audio == b"mp3-audio"
    assert result.media_type == "audio/mpeg"
    assert result.format == "mp3"
    assert result.provider == "elevenlabs"
    assert result.model == "custom-model"
    assert "/text-to-speech/voice%2Fid?output_format=mp3_44100_128" in str(seen["url"])
    assert seen["payload"] == {"text": "Hello", "model_id": "custom-model"}
    assert seen["headers"] == {"xi-api-key": "key"}


def test_elevenlabs_health_and_errors_are_actionable() -> None:
    def auth(*args: object) -> dict[str, object]:
        raise ElevenLabsAuthError("bad key")

    provider = ElevenLabsTTSProvider(api_key="key", request_json=auth)
    health = provider.health()
    assert not health.healthy
    assert "bad key" in health.message

    empty = ElevenLabsTTSProvider(api_key="key", request_binary=lambda *args: b"")
    with pytest.raises(ElevenLabsTTSError, match="empty audio"):
        empty.synthesize(TTSRequest("Hello", "v1"))


def test_elevenlabs_rejects_malformed_voice_response() -> None:
    provider = ElevenLabsTTSProvider(api_key="key", request_json=lambda *args: {"not_voices": []})
    with pytest.raises(ElevenLabsTTSError, match="missing voices"):
        provider.voices()
