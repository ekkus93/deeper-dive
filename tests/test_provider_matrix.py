from __future__ import annotations

from collections.abc import Iterable

import pytest

from deeper_dive.elevenlabs_tts import ElevenLabsTTSProvider
from deeper_dive.kitten_tts import KittenTTSMicroProvider
from deeper_dive.llama_server_llm import LlamaServerLLMProvider
from deeper_dive.llm import LLMMessage, LLMRequest
from deeper_dive.ollama_llm import OllamaLLMProvider
from deeper_dive.openai_compatible_tts import OpenAICompatibleTTSProvider
from deeper_dive.openai_llm import OpenAILLMProvider
from deeper_dive.openai_tts import OpenAITTSProvider
from deeper_dive.tts import TTSRequest


def _llm_request() -> LLMRequest:
    return LLMRequest((LLMMessage("user", "Summarize the fixture."),))


def test_openai_llm_contract_without_network() -> None:
    def request(method: str, url: str, payload: object, headers: object, timeout: float) -> dict[str, object]:
        if method == "GET":
            return {"data": [{"id": "gpt-test"}]}
        return {"output_text": "openai answer", "model": "gpt-test", "usage": {"input_tokens": 3, "output_tokens": 2}}

    provider = OpenAILLMProvider(api_key="test", model="gpt-test", request_json=request)
    assert provider.health().healthy
    assert provider.models()[0].model == "gpt-test"
    assert provider.generate(_llm_request()).text == "openai answer"


def test_ollama_llm_contract_without_network() -> None:
    def request(method: str, url: str, payload: object, timeout: float) -> dict[str, object]:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen-test"}]}
        if url.endswith("/api/version"):
            return {"version": "test"}
        return {"message": {"content": "ollama answer"}, "model": "qwen-test"}

    provider = OllamaLLMProvider(model="qwen-test", request_json=request)
    assert provider.health().healthy
    assert provider.models()[0].model == "qwen-test"
    assert provider.generate(_llm_request()).text == "ollama answer"


def test_llama_server_contract_without_network() -> None:
    def request(method: str, url: str, payload: object, timeout: float) -> dict[str, object]:
        if url.endswith("/health"):
            return {"status": "ok"}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "gguf-test"}]}
        return {"choices": [{"message": {"content": "llama answer"}}], "model": "gguf-test"}

    provider = LlamaServerLLMProvider(model="gguf-test", request_json=request)
    assert provider.health().healthy
    assert provider.models()[0].model == "gguf-test"
    assert provider.generate(_llm_request()).text == "llama answer"


class _KittenRuntime:
    available_voices = ("Bella",)

    def generate(self, text: str, *, voice: str, speed: float = 1.0) -> Iterable[float]:
        return (0.0, 0.1, -0.1, 0.0)


def test_kitten_tts_contract_without_runtime_download() -> None:
    provider = KittenTTSMicroProvider(runtime_factory=lambda model: _KittenRuntime())
    assert provider.health().healthy
    result = provider.synthesize(TTSRequest("hello", "Bella"))
    assert result.provider == "kitten"
    assert result.media_type == "audio/wav"
    assert result.audio.startswith(b"RIFF")


def test_openai_tts_contract_without_network() -> None:
    provider = OpenAITTSProvider(
        api_key="test",
        request_binary=lambda url, payload, headers, timeout: b"audio",
    )
    assert provider.health().healthy
    result = provider.synthesize(TTSRequest("hello", "alloy", response_format="mp3"))
    assert result.provider == "openai"
    assert result.audio == b"audio"


def test_openai_compatible_tts_contract_without_network() -> None:
    provider = OpenAICompatibleTTSProvider(
        provider_id="compatible-test",
        base_url="http://127.0.0.1:9999/v1",
        model="tts-test",
        voices=("voice-test",),
        request_binary=lambda url, payload, headers, timeout: (b"audio", "audio/wav"),
    )
    assert provider.health().healthy
    result = provider.synthesize(TTSRequest("hello", "voice-test"))
    assert result.provider == "compatible-test"
    assert result.audio == b"audio"


def test_elevenlabs_tts_contract_without_network() -> None:
    provider = ElevenLabsTTSProvider(
        api_key="test",
        request_json=lambda url, headers, timeout: {"voices": [{"voice_id": "v1", "name": "Test Voice"}]},
        request_binary=lambda url, payload, headers, timeout: b"audio",
    )
    assert provider.health().healthy
    assert provider.voices()[0].id == "v1"
    result = provider.synthesize(TTSRequest("hello", "v1", response_format="mp3"))
    assert result.provider == "elevenlabs"
    assert result.audio == b"audio"
