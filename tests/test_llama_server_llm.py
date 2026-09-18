from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from deeper_dive.llama_server_llm import LlamaServerError, LlamaServerLLMProvider
from deeper_dive.llm import LLMMessage, LLMRequest


def test_llama_server_health_models_generation_and_structured_output() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None, float]] = []

    def request(method: str, url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
        calls.append((method, url, payload, timeout))
        if url.endswith("/health"):
            return {"status": "ok"}
        if url.endswith("/models"):
            return {"data": [{"id": "local.gguf", "meta": {"n_ctx_train": 32768}}]}
        return {
            "model": "local.gguf",
            "choices": [{"message": {"content": '{"answer":"yes"}'}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3},
        }

    provider = LlamaServerLLMProvider(
        model="local.gguf", base_url="http://llama:8080/", request_json=request
    )
    assert provider.health().healthy
    models = provider.models()
    assert models[0].model == "local.gguf"
    assert models[0].capabilities.max_context_tokens == 32768
    response = provider.generate(
        LLMRequest(
            (LLMMessage("user", "answer"),),
            response_schema={"type": "object"},
            temperature=0.2,
            max_output_tokens=50,
        )
    )
    assert response.structured == {"answer": "yes"}
    assert response.usage.input_tokens == 4
    payload = calls[-1][2]
    assert payload is not None
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["max_tokens"] == 50


def test_llama_server_stream_and_custom_endpoint_paths() -> None:
    def stream(url: str, payload: dict[str, Any], timeout: float) -> Iterator[dict[str, Any]]:
        assert url == "http://host/custom/chat"
        assert payload["stream"] is True
        yield {"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    provider = LlamaServerLLMProvider(
        model="m", base_url="http://host", chat_path="custom/chat", request_stream=stream
    )
    chunks = list(provider.stream(LLMRequest((LLMMessage("user", "hi"),))))
    assert [chunk.text for chunk in chunks] == ["hello", ""]
    assert chunks[-1].done


def test_llama_server_unavailable_is_recoverable_health_error() -> None:
    def unavailable(method: str, url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
        raise LlamaServerError("llama-server is unavailable")

    provider = LlamaServerLLMProvider(model="m", request_json=unavailable)
    health = provider.health()
    assert not health.healthy
    assert "unavailable" in health.message


def test_llama_server_common_malformed_shapes_are_errors() -> None:
    def malformed(method: str, url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
        if url.endswith("/models"):
            return {"data": "bad"}
        return {"choices": []}

    provider = LlamaServerLLMProvider(model="m", request_json=malformed)
    try:
        provider.models()
    except LlamaServerError:
        pass
    else:
        raise AssertionError("malformed model response should fail")
    try:
        provider.generate(LLMRequest((LLMMessage("user", "hi"),)))
    except LlamaServerError:
        pass
    else:
        raise AssertionError("malformed generation response should fail")
