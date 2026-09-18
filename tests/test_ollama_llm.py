from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from deeper_dive.llm import LLMMessage, LLMRequest
from deeper_dive.ollama_llm import OllamaLLMError, OllamaLLMProvider


def req(*, schema: dict[str, object] | None = None) -> LLMRequest:
    return LLMRequest((LLMMessage("user", "hello"),), response_schema=schema)


def test_native_generation_usage_and_structured_output() -> None:
    seen: dict[str, Any] = {}

    def fake(
        method: str, url: str, payload: dict[str, Any] | None, timeout: float
    ) -> dict[str, Any]:
        assert url.endswith("/api/chat")
        assert payload is not None
        seen.update(payload)
        return {
            "model": "qwen-test",
            "message": {"role": "assistant", "content": '{"answer":"yes"}'},
            "prompt_eval_count": 12,
            "eval_count": 4,
        }

    schema: dict[str, object] = {"type": "object", "properties": {"answer": {"type": "string"}}}
    provider = OllamaLLMProvider(model="qwen-test", request_json=fake)
    response = provider.generate(req(schema=schema))
    assert response.structured == {"answer": "yes"}
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 4
    assert seen["format"] == schema
    assert seen["stream"] is False


def test_native_model_discovery_captures_context_metadata() -> None:
    def fake(
        method: str, url: str, payload: dict[str, Any] | None, timeout: float
    ) -> dict[str, Any]:
        return {
            "models": [
                {"name": "qwen:latest", "details": {"context_length": 32768}},
                {"model": "gemma:latest", "details": {}},
            ]
        }

    provider = OllamaLLMProvider(model="qwen:latest", request_json=fake)
    models = provider.models()
    assert [model.model for model in models] == ["gemma:latest", "qwen:latest"]
    assert models[1].capabilities.max_context_tokens == 32768
    assert all(model.capabilities.structured_output for model in models)


def test_health_uses_native_version_endpoint_and_recovers_failure() -> None:
    calls: list[str] = []

    def healthy(
        method: str, url: str, payload: dict[str, Any] | None, timeout: float
    ) -> dict[str, Any]:
        calls.append(url)
        return {"version": "1.0"}

    provider = OllamaLLMProvider(model="qwen", request_json=healthy)
    assert provider.health().healthy is True
    assert calls == ["http://127.0.0.1:11434/api/version"]

    def failed(
        method: str, url: str, payload: dict[str, Any] | None, timeout: float
    ) -> dict[str, Any]:
        raise OllamaLLMError("offline")

    assert OllamaLLMProvider(model="qwen", request_json=failed).health().healthy is False


def test_native_streaming() -> None:
    def stream(url: str, payload: dict[str, Any], timeout: float) -> Iterator[dict[str, Any]]:
        assert url.endswith("/api/chat")
        yield {"message": {"content": "hello "}, "done": False}
        yield {"message": {"content": "world"}, "done": True}

    provider = OllamaLLMProvider(model="qwen", request_stream=stream)
    chunks = list(provider.stream(req()))
    assert [(chunk.text, chunk.done) for chunk in chunks] == [
        ("hello ", False),
        ("world", False),
        ("", True),
    ]


def test_malformed_generation_response_is_rejected() -> None:
    def fake(
        method: str, url: str, payload: dict[str, Any] | None, timeout: float
    ) -> dict[str, Any]:
        return {"done": True}

    provider = OllamaLLMProvider(model="qwen", request_json=fake)
    with pytest.raises(OllamaLLMError, match="message content"):
        provider.generate(req())
