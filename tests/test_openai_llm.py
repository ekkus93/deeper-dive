from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from deeper_dive.llm import LLMMessage, LLMRequest
from deeper_dive.openai_llm import (
    OpenAIAuthError,
    OpenAILLMError,
    OpenAILLMProvider,
    OpenAIRateLimitError,
    OpenAITimeoutError,
)


def request(*, schema: dict[str, object] | None = None) -> LLMRequest:
    return LLMRequest((LLMMessage("user", "hello"),), response_schema=schema)


def test_generate_normalizes_response_usage_and_latency() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake(method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        calls.append((method, url, payload))
        assert headers["Authorization"] == "Bearer test-key"
        assert timeout == 4.0
        return {
            "model": "gpt-test",
            "output_text": "answer",
            "usage": {"input_tokens": 3, "output_tokens": 2},
        }

    provider = OpenAILLMProvider(api_key="test-key", model="gpt-test", timeout=4.0, request_json=fake)
    response = provider.generate(request())
    assert response.text == "answer"
    assert response.model == "gpt-test"
    assert response.usage.input_tokens == 3
    assert response.usage.output_tokens == 2
    assert calls[0][0:2] == ("POST", "https://api.openai.com/v1/responses")
    assert provider.last_metrics is not None
    assert provider.last_metrics.attempts == 1
    assert provider.last_metrics.latency_seconds >= 0


def test_structured_output_requests_schema_and_parses_json() -> None:
    seen: dict[str, Any] = {}

    def fake(method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        assert payload is not None
        seen.update(payload)
        return {"model": "gpt-test", "output_text": '{"topic":"science"}'}

    schema: dict[str, object] = {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
        "additionalProperties": False,
    }
    provider = OpenAILLMProvider(api_key="k", model="gpt-test", request_json=fake)
    response = provider.generate(request(schema=schema))
    assert response.structured == {"topic": "science"}
    assert seen["text"] == {
        "format": {
            "type": "json_schema",
            "name": "deeper_dive_response",
            "schema": schema,
            "strict": True,
        }
    }


def test_stream_normalizes_text_deltas_and_completion() -> None:
    def stream(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> Iterator[dict[str, Any]]:
        assert payload["stream"] is True
        yield {"type": "response.output_text.delta", "delta": "hel"}
        yield {"type": "response.output_text.delta", "delta": "lo"}
        yield {"type": "response.completed"}

    provider = OpenAILLMProvider(api_key="k", model="gpt-test", request_stream=stream)
    chunks = list(provider.stream(request()))
    assert [(chunk.text, chunk.done) for chunk in chunks] == [
        ("hel", False),
        ("lo", False),
        ("", True),
    ]


def test_timeout_and_rate_limit_retry_are_bounded() -> None:
    attempts = 0
    sleeps: list[float] = []

    def fake(method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OpenAITimeoutError("timeout")
        if attempts == 2:
            raise OpenAIRateLimitError("rate")
        return {"model": "gpt-test", "output_text": "ok"}

    provider = OpenAILLMProvider(api_key="k", model="gpt-test", max_retries=2, request_json=fake, sleep=sleeps.append)
    assert provider.generate(request()).text == "ok"
    assert attempts == 3
    assert sleeps == [0.25, 0.5]

    def always_timeout(method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        raise OpenAITimeoutError("timeout")

    provider = OpenAILLMProvider(api_key="k", model="gpt-test", max_retries=1, request_json=always_timeout, sleep=lambda _: None)
    with pytest.raises(OpenAITimeoutError):
        provider.generate(request())


def test_auth_error_is_not_retried() -> None:
    attempts = 0

    def fake(method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise OpenAIAuthError("bad key")

    provider = OpenAILLMProvider(api_key="bad", model="gpt-test", request_json=fake)
    with pytest.raises(OpenAIAuthError):
        provider.generate(request())
    assert attempts == 1


def test_malformed_response_is_rejected() -> None:
    def fake(method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        return {"model": "gpt-test", "output": [{"content": [{"type": "refusal"}]}]}

    provider = OpenAILLMProvider(api_key="k", model="gpt-test", request_json=fake)
    with pytest.raises(OpenAILLMError, match="no output text"):
        provider.generate(request())


def test_model_discovery_and_health() -> None:
    def fake(method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        assert method == "GET"
        return {"data": [{"id": "z-model"}, {"id": "a-model"}]}

    provider = OpenAILLMProvider(api_key="k", model="gpt-test", request_json=fake)
    assert [model.model for model in provider.models()] == ["a-model", "z-model"]
    assert provider.health().healthy is True
