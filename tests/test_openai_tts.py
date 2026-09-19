from __future__ import annotations

from typing import Any

import pytest

from deeper_dive.openai_tts import (
    OpenAITTSAuthError,
    OpenAITTSError,
    OpenAITTSProvider,
    OpenAITTSRateLimitError,
    OpenAITTSTimeoutError,
)
from deeper_dive.tts import TTSRequest


def test_openai_tts_synthesizes_and_normalizes_audio() -> None:
    calls: list[tuple[str, dict[str, object], dict[str, str], float]] = []

    def request(
        url: str, payload: dict[str, object], headers: dict[str, str], timeout: float
    ) -> bytes:
        calls.append((url, payload, headers, timeout))
        return b"audio-bytes"

    provider = OpenAITTSProvider(api_key="test-key", request_binary=request)
    result = provider.synthesize(TTSRequest("Hello evidence", "alloy", response_format="mp3"))

    assert result.audio == b"audio-bytes"
    assert result.media_type == "audio/mpeg"
    assert result.format == "mp3"
    assert result.provider == "openai"
    assert result.voice == "alloy"
    assert result.model == "gpt-4o-mini-tts"
    assert calls[0][0] == "https://api.openai.com/v1/audio/speech"
    assert calls[0][1] == {
        "model": "gpt-4o-mini-tts",
        "input": "Hello evidence",
        "voice": "alloy",
        "response_format": "mp3",
    }
    assert calls[0][2]["Authorization"] == "Bearer test-key"


def test_openai_tts_exposes_static_voice_capability_and_model_override() -> None:
    seen: dict[str, Any] = {}

    def request(
        url: str, payload: dict[str, object], headers: dict[str, str], timeout: float
    ) -> bytes:
        seen.update(payload)
        return b"wav"

    provider = OpenAITTSProvider(api_key="key", request_binary=request)
    assert provider.health().healthy
    assert "alloy" in {voice.id for voice in provider.voices()}

    result = provider.synthesize(TTSRequest("Hi", "nova", model="tts-1", response_format="wav"))
    assert result.model == "tts-1"
    assert seen["model"] == "tts-1"


@pytest.mark.parametrize("error", [OpenAITTSRateLimitError("rate"), OpenAITTSTimeoutError("slow")])
def test_openai_tts_retries_transient_failures(error: OpenAITTSError) -> None:
    attempts = 0
    sleeps: list[float] = []

    def request(*args: object) -> bytes:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise error
        return b"ok"

    provider = OpenAITTSProvider(
        api_key="key", request_binary=request, max_retries=1, sleep=sleeps.append
    )
    assert provider.synthesize(TTSRequest("Hi", "echo")).audio == b"ok"
    assert attempts == 2
    assert sleeps == [0.25]


def test_openai_tts_does_not_retry_auth_failure() -> None:
    def request(*args: object) -> bytes:
        raise OpenAITTSAuthError("bad key")

    provider = OpenAITTSProvider(api_key="key", request_binary=request, max_retries=2)
    with pytest.raises(OpenAITTSAuthError, match="bad key"):
        provider.synthesize(TTSRequest("Hi", "alloy"))


def test_openai_tts_rejects_invalid_input_and_empty_audio() -> None:
    provider = OpenAITTSProvider(api_key="key", request_binary=lambda *args: b"")
    with pytest.raises(ValueError, match="text"):
        provider.synthesize(TTSRequest(" ", "alloy"))
    with pytest.raises(ValueError, match="voice"):
        provider.synthesize(TTSRequest("Hi", "unknown"))
    with pytest.raises(ValueError, match="format"):
        provider.synthesize(TTSRequest("Hi", "alloy", response_format="avi"))
    with pytest.raises(OpenAITTSError, match="empty audio"):
        provider.synthesize(TTSRequest("Hi", "alloy"))
