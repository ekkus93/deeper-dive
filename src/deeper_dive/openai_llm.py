"""OpenAI Responses API adapter for the normalized LLM provider contract."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from deeper_dive.llm import (
    LLMCapabilities,
    LLMModel,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ProviderHealth,
)


class OpenAILLMError(RuntimeError):
    """Normalized OpenAI provider failure."""


class OpenAIAuthError(OpenAILLMError):
    pass


class OpenAIRateLimitError(OpenAILLMError):
    pass


class OpenAITimeoutError(OpenAILLMError):
    pass


JsonRequest = Callable[[str, str, dict[str, Any] | None, dict[str, str], float], dict[str, Any]]
StreamRequest = Callable[[str, dict[str, Any], dict[str, str], float], Iterator[dict[str, Any]]]
Sleep = Callable[[float], None]


def _json_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    request = Request(
        url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured API URL
            value = json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise OpenAITimeoutError("OpenAI request timed out") from exc
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise OpenAIAuthError("OpenAI authentication failed") from exc
        if exc.code == 429:
            raise OpenAIRateLimitError("OpenAI rate limit exceeded") from exc
        raise OpenAILLMError(f"OpenAI HTTP error {exc.code}") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise OpenAITimeoutError("OpenAI request timed out") from exc
        raise OpenAILLMError(f"OpenAI connection failed: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OpenAILLMError("OpenAI returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise OpenAILLMError("OpenAI returned a non-object response")
    return value


def _stream_request(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> Iterator[dict[str, Any]]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured API URL
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                if isinstance(event, dict):
                    yield event
    except TimeoutError as exc:
        raise OpenAITimeoutError("OpenAI stream timed out") from exc
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise OpenAIAuthError("OpenAI authentication failed") from exc
        if exc.code == 429:
            raise OpenAIRateLimitError("OpenAI rate limit exceeded") from exc
        raise OpenAILLMError(f"OpenAI HTTP error {exc.code}") from exc
    except (URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OpenAILLMError("OpenAI stream failed or was malformed") from exc


@dataclass(frozen=True, slots=True)
class OpenAIRequestMetrics:
    latency_seconds: float
    attempts: int


class OpenAILLMProvider:
    """OpenAI adapter using the current Responses API wire format."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        max_retries: int = 2,
        request_json: JsonRequest = _json_request,
        request_stream: StreamRequest = _stream_request,
        sleep: Sleep = time.sleep,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._request = request_json
        self._request_stream = request_stream
        self._sleep = sleep
        self.last_metrics: OpenAIRequestMetrics | None = None

    @property
    def provider_id(self) -> str:
        return "openai"

    def health(self) -> ProviderHealth:
        try:
            self.models()
        except OpenAILLMError as exc:
            return ProviderHealth(False, str(exc))
        return ProviderHealth(True, "ready")

    def models(self) -> tuple[LLMModel, ...]:
        value, _, _ = self._with_retry("GET", "/models", None)
        data = value.get("data")
        if not isinstance(data, list):
            raise OpenAILLMError("OpenAI model response is missing data")
        models: list[LLMModel] = []
        for item in data:
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                models.append(
                    LLMModel(
                        "openai",
                        item["id"],
                        LLMCapabilities(
                            streaming=True, structured_output=True, model_discovery=True
                        ),
                    )
                )
        return tuple(sorted(models, key=lambda item: item.model))

    def generate(self, request: LLMRequest) -> LLMResponse:
        payload = self._payload(request, stream=False)
        started = time.monotonic()
        value, attempts, _ = self._with_retry("POST", "/responses", payload)
        self.last_metrics = OpenAIRequestMetrics(time.monotonic() - started, attempts)
        text = self._response_text(value)
        usage = self._usage(value)
        structured: Mapping[str, object] | None = None
        if request.response_schema is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise OpenAILLMError("OpenAI structured response was not valid JSON") from exc
            if not isinstance(parsed, dict):
                raise OpenAILLMError("OpenAI structured response was not an object")
            structured = parsed
        model = value.get("model")
        return LLMResponse(
            text,
            model if isinstance(model, str) else request.model or self._model,
            usage,
            structured,
        )

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        payload = self._payload(request, stream=True)
        headers = self._headers()
        for event in self._request_stream(
            f"{self._base_url}/responses", payload, headers, self._timeout
        ):
            event_type = event.get("type")
            if event_type == "response.output_text.delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    yield LLMStreamChunk(delta)
            elif event_type in {"response.completed", "response.failed", "response.incomplete"}:
                if event_type == "response.completed":
                    yield LLMStreamChunk("", done=True)
                else:
                    raise OpenAILLMError(f"OpenAI stream ended with {event_type}")

    def _with_retry(
        self, method: str, path: str, payload: dict[str, Any] | None
    ) -> tuple[dict[str, Any], int, float]:
        started = time.monotonic()
        attempts = 0
        while True:
            attempts += 1
            try:
                value = self._request(
                    method,
                    f"{self._base_url}{path}",
                    payload,
                    self._headers(),
                    self._timeout,
                )
                return value, attempts, time.monotonic() - started
            except (OpenAIRateLimitError, OpenAITimeoutError):
                if attempts > self._max_retries:
                    raise
                self._sleep(min(0.25 * (2 ** (attempts - 1)), 2.0))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _payload(self, request: LLMRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._model,
            "input": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
            "stream": stream,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens
        if request.response_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "deeper_dive_response",
                    "schema": dict(request.response_schema),
                    "strict": True,
                }
            }
        return payload

    @staticmethod
    def _response_text(value: Mapping[str, Any]) -> str:
        direct = value.get("output_text")
        if isinstance(direct, str):
            return direct
        output = value.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, Mapping):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if isinstance(part, Mapping) and part.get("type") == "output_text":
                        text = part.get("text")
                        if isinstance(text, str):
                            parts.append(text)
            if parts:
                return "".join(parts)
        raise OpenAILLMError("OpenAI response contained no output text")

    @staticmethod
    def _usage(value: Mapping[str, Any]) -> LLMUsage:
        usage = value.get("usage")
        if not isinstance(usage, Mapping):
            return LLMUsage()
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        return LLMUsage(
            input_tokens if isinstance(input_tokens, int) else 0,
            output_tokens if isinstance(output_tokens, int) else 0,
        )
