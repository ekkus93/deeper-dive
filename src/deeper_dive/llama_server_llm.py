"""llama.cpp llama-server adapter for the normalized LLM provider contract."""

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


class LlamaServerError(RuntimeError):
    """Recoverable llama-server provider/configuration failure."""


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
    except HTTPError as exc:
        raise LlamaServerError(f"llama-server HTTP error {exc.code}") from exc
    except (TimeoutError, URLError) as exc:
        raise LlamaServerError(f"llama-server is unavailable: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LlamaServerError("llama-server returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise LlamaServerError("llama-server returned a non-object response")
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
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                value = json.loads(data)
                if isinstance(value, dict):
                    yield value
    except (TimeoutError, URLError, HTTPError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LlamaServerError(f"llama-server stream failed: {exc}") from exc


class LlamaServerLLMProvider:
    """Native llama-server adapter using its health and OpenAI-style v1 endpoints."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:8080",
        timeout: float = 60.0,
        health_path: str = "/health",
        models_path: str = "/v1/models",
        chat_path: str = "/v1/chat/completions",
        request_json: JsonRequest = _json_request,
        request_stream: StreamRequest = _stream_request,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._health_path = self._path(health_path)
        self._models_path = self._path(models_path)
        self._chat_path = self._path(chat_path)
        self._request = request_json
        self._request_stream = request_stream

    @property
    def provider_id(self) -> str:
        return "llama-server"

    def health(self) -> ProviderHealth:
        try:
            value = self._request("GET", self._url(self._health_path), None, self._timeout)
        except LlamaServerError as exc:
            return ProviderHealth(False, str(exc))
        status = value.get("status")
        healthy = status in {None, "ok", "ready"}
        return ProviderHealth(healthy, "ready" if healthy else str(status))

    def models(self) -> tuple[LLMModel, ...]:
        value = self._request("GET", self._url(self._models_path), None, self._timeout)
        data = value.get("data")
        if not isinstance(data, list):
            raise LlamaServerError("llama-server model response is missing data")
        result: list[LLMModel] = []
        for item in data:
            if not isinstance(item, Mapping):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str):
                continue
            meta = item.get("meta")
            context = None
            if isinstance(meta, Mapping):
                candidate = meta.get("n_ctx_train") or meta.get("n_ctx")
                if isinstance(candidate, int):
                    context = candidate
            result.append(
                LLMModel(
                    self.provider_id,
                    model_id,
                    LLMCapabilities(True, True, True, context),
                )
            )
        return tuple(sorted(result, key=lambda item: item.model))

    def generate(self, request: LLMRequest) -> LLMResponse:
        value = self._request(
            "POST", self._url(self._chat_path), self._payload(request, stream=False), self._timeout
        )
        text = self._choice_text(value)
        structured: Mapping[str, object] | None = None
        if request.response_schema is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise LlamaServerError(
                    "llama-server structured response was not valid JSON"
                ) from exc
            if not isinstance(parsed, dict):
                raise LlamaServerError("llama-server structured response was not an object")
            structured = parsed
        usage = value.get("usage")
        prompt_tokens = completion_tokens = 0
        if isinstance(usage, Mapping):
            prompt_tokens = self._int(usage.get("prompt_tokens"))
            completion_tokens = self._int(usage.get("completion_tokens"))
        model = value.get("model")
        return LLMResponse(
            text,
            model if isinstance(model, str) else request.model or self._model,
            LLMUsage(prompt_tokens, completion_tokens),
            structured,
        )

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        for value in self._request_stream(
            self._url(self._chat_path), self._payload(request, stream=True), self._timeout
        ):
            choices = value.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
                continue
            choice = choices[0]
            delta = choice.get("delta")
            if isinstance(delta, Mapping):
                content = delta.get("content")
                if isinstance(content, str) and content:
                    yield LLMStreamChunk(content)
            if choice.get("finish_reason") is not None:
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
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "deeper_dive_response",
                    "schema": dict(request.response_schema),
                },
            }
        return payload

    @staticmethod
    def _choice_text(value: Mapping[str, object]) -> str:
        choices = value.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise LlamaServerError("llama-server response is missing choices")
        message = choices[0].get("message")
        if not isinstance(message, Mapping):
            raise LlamaServerError("llama-server response is missing message content")
        content = message.get("content")
        if not isinstance(content, str):
            raise LlamaServerError("llama-server response is missing message content")
        return content

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    @staticmethod
    def _path(path: str) -> str:
        return path if path.startswith("/") else f"/{path}"

    @staticmethod
    def _int(value: object) -> int:
        return value if isinstance(value, int) else 0
