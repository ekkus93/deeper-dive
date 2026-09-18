"""Native Ollama API adapter for the normalized LLM provider contract."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
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


class OllamaLLMError(RuntimeError):
    """Recoverable native Ollama provider failure."""


JsonRequest = Callable[[str, str, dict[str, Any] | None, float], dict[str, Any]]
StreamRequest = Callable[[str, dict[str, Any], float], Iterator[dict[str, Any]]]


def _json_request(
    method: str, url: str, payload: dict[str, Any] | None, timeout: float
) -> dict[str, Any]:
    request = Request(
        url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured local endpoint
            value = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, URLError) as exc:
        raise OllamaLLMError(f"Ollama is unavailable: {exc}") from exc
    except HTTPError as exc:
        raise OllamaLLMError(f"Ollama HTTP error {exc.code}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OllamaLLMError("Ollama returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise OllamaLLMError("Ollama returned a non-object response")
    return value


def _stream_request(url: str, payload: dict[str, Any], timeout: float) -> Iterator[dict[str, Any]]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured local endpoint
            for raw_line in response:
                if not raw_line.strip():
                    continue
                value = json.loads(raw_line.decode("utf-8"))
                if isinstance(value, dict):
                    yield value
    except (TimeoutError, URLError, HTTPError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OllamaLLMError(f"Ollama stream failed: {exc}") from exc


class OllamaLLMProvider:
    """Native Ollama /api adapter, independent of OpenAI compatibility mode."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 60.0,
        request_json: JsonRequest = _json_request,
        request_stream: StreamRequest = _stream_request,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._request = request_json
        self._request_stream = request_stream

    @property
    def provider_id(self) -> str:
        return "ollama"

    def health(self) -> ProviderHealth:
        try:
            self._request("GET", f"{self._base_url}/api/version", None, self._timeout)
        except OllamaLLMError as exc:
            return ProviderHealth(False, str(exc))
        return ProviderHealth(True, "ready")

    def models(self) -> tuple[LLMModel, ...]:
        value = self._request("GET", f"{self._base_url}/api/tags", None, self._timeout)
        data = value.get("models")
        if not isinstance(data, list):
            raise OllamaLLMError("Ollama model response is missing models")
        result: list[LLMModel] = []
        for item in data:
            if not isinstance(item, Mapping):
                continue
            name = item.get("name") or item.get("model")
            if not isinstance(name, str):
                continue
            details = item.get("details")
            context = None
            if isinstance(details, Mapping):
                candidate = details.get("context_length")
                if isinstance(candidate, int):
                    context = candidate
            result.append(
                LLMModel(
                    "ollama",
                    name,
                    LLMCapabilities(
                        streaming=True,
                        structured_output=True,
                        model_discovery=True,
                        max_context_tokens=context,
                    ),
                )
            )
        return tuple(sorted(result, key=lambda item: item.model))

    def generate(self, request: LLMRequest) -> LLMResponse:
        payload = self._payload(request, stream=False)
        value = self._request("POST", f"{self._base_url}/api/chat", payload, self._timeout)
        message = value.get("message")
        if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
            raise OllamaLLMError("Ollama response is missing message content")
        text = message["content"]
        structured: Mapping[str, object] | None = None
        if request.response_schema is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise OllamaLLMError("Ollama structured response was not valid JSON") from exc
            if not isinstance(parsed, dict):
                raise OllamaLLMError("Ollama structured response was not an object")
            structured = parsed
        model = value.get("model")
        return LLMResponse(
            text,
            model if isinstance(model, str) else request.model or self._model,
            LLMUsage(
                self._int(value.get("prompt_eval_count")),
                self._int(value.get("eval_count")),
            ),
            structured,
        )

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        payload = self._payload(request, stream=True)
        for value in self._request_stream(f"{self._base_url}/api/chat", payload, self._timeout):
            message = value.get("message")
            if isinstance(message, Mapping):
                content = message.get("content")
                if isinstance(content, str) and content:
                    yield LLMStreamChunk(content)
            if value.get("done") is True:
                yield LLMStreamChunk("", done=True)
                return

    def _payload(self, request: LLMRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._model,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
            "stream": stream,
        }
        options: dict[str, object] = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            options["num_predict"] = request.max_output_tokens
        if options:
            payload["options"] = options
        if request.response_schema is not None:
            payload["format"] = dict(request.response_schema)
        return payload

    @staticmethod
    def _int(value: object) -> int:
        return value if isinstance(value, int) else 0
