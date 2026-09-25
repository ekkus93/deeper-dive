"""Normalized LLM provider contract, registry, and deterministic fake provider."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LLMCapabilities:
    """Capabilities exposed by a provider/model combination."""

    streaming: bool = False
    structured_output: bool = False
    model_discovery: bool = False
    max_context_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class LLMModel:
    """Normalized model identity and capabilities."""

    provider: str
    model: str
    capabilities: LLMCapabilities = field(default_factory=LLMCapabilities)

    @property
    def identity(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    messages: tuple[LLMMessage, ...]
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    response_schema: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    structured: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class LLMStreamChunk:
    text: str
    done: bool = False


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    healthy: bool
    message: str = ""


class LLMProvider(Protocol):
    """Provider-neutral interface consumed by orchestration."""

    @property
    def provider_id(self) -> str: ...

    def health(self) -> ProviderHealth: ...

    def models(self) -> tuple[LLMModel, ...]: ...

    def generate(self, request: LLMRequest) -> LLMResponse: ...

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]: ...


class LLMProviderRegistry:
    """Configuration boundary mapping stable provider IDs to provider instances."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        if not provider.provider_id:
            raise ValueError("provider_id must not be empty")
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> LLMProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"unknown LLM provider: {provider_id}") from exc

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def health(self) -> dict[str, ProviderHealth]:
        return {
            provider_id: self._providers[provider_id].health()
            for provider_id in self.provider_ids()
        }

    def models(self) -> dict[str, tuple[LLMModel, ...]]:
        return {
            provider_id: self._providers[provider_id].models()
            for provider_id in self.provider_ids()
        }


class FakeLLMProvider:
    """Deterministic provider for orchestration and integration tests."""

    DEFAULT_RESPONSE = "fake response"

    def __init__(
        self,
        *,
        provider_id: str = "fake",
        model: str = "fake-v1",
        response: str = DEFAULT_RESPONSE,
    ) -> None:
        self._provider_id = provider_id
        self._model = LLMModel(
            provider_id,
            model,
            LLMCapabilities(streaming=True, structured_output=True, model_discovery=True),
        )
        self.response = response
        self.requests: list[LLMRequest] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def health(self) -> ProviderHealth:
        return ProviderHealth(True, "ready")

    def models(self) -> tuple[LLMModel, ...]:
        return (self._model,)

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        model = request.model or self._model.model
        text = self._response_for(request)
        input_tokens = sum(len(message.content.split()) for message in request.messages)
        output_tokens = len(text.split())
        return LLMResponse(text, model, LLMUsage(input_tokens, output_tokens))

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        self.requests.append(request)
        words = self._response_for(request).split()
        for index, word in enumerate(words):
            suffix = "" if index == len(words) - 1 else " "
            yield LLMStreamChunk(word + suffix, done=index == len(words) - 1)

    def _response_for(self, request: LLMRequest) -> str:
        prompt = "\n".join(message.content for message in request.messages).lower()
        if "choose the next podcast host turn" in prompt and "director decision" in prompt:
            return self._director_decision_response(request)
        if "verify generated podcast transcript" in prompt and "accepted" in prompt:
            if self.response != self.DEFAULT_RESPONSE:
                try:
                    payload = json.loads(self.response)
                except json.JSONDecodeError:
                    return self.response
                if isinstance(payload, dict) and "accepted" in payload:
                    return self.response
            return self._verification_response()
        if "generate one podcast host turn" in prompt:
            if self.response == self.DEFAULT_RESPONSE:
                return self._host_turn_response(request)
            try:
                payload = json.loads(self.response)
            except json.JSONDecodeError:
                return self.response
            if isinstance(payload, dict) and isinstance(payload.get("segments"), list):
                return self._host_turn_response(request)
            return self.response
        if "identify research gaps" in prompt and "gaps array" in prompt:
            try:
                payload = json.loads(self.response)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("gaps"), list):
                return self.response
            return self._research_gap_response(request)
        return self.response

    @staticmethod
    def _director_decision_response(request: LLMRequest) -> str:
        try:
            payload = json.loads(request.messages[-1].content)
        except (IndexError, json.JSONDecodeError):
            payload = {}
        host_ids = payload.get("host_ids", []) if isinstance(payload, dict) else []
        speaker_id = str(host_ids[0]) if host_ids else ""
        evidence_ids = (
            payload.get("available_evidence_ids", []) if isinstance(payload, dict) else []
        )
        return json.dumps(
            {
                "speaker_id": speaker_id,
                "intent": "Configured fake directing decision marker.",
                "evidence_ids": evidence_ids if isinstance(evidence_ids, list) else [],
                "target_duration_seconds": 45,
                "target_words": 80,
                "handoff_instruction": "Continue with configured provider-backed generation.",
                "segment_signal": "continue",
            },
            sort_keys=True,
        )

    @staticmethod
    def _verification_response() -> str:
        return json.dumps(
            {"accepted": True, "notes": "Configured fake verification marker."},
            sort_keys=True,
        )

    @staticmethod
    def _host_turn_response(request: LLMRequest) -> str:
        try:
            payload = json.loads(request.messages[-1].content)
        except (IndexError, json.JSONDecodeError):
            payload = {}
        speaker_id = str(payload.get("speaker_id", "")) if isinstance(payload, dict) else ""
        evidence_ids = payload.get("evidence_ids", []) if isinstance(payload, dict) else []
        intent = str(payload.get("intent", "")) if isinstance(payload, dict) else ""
        marker = "Configured fake provider host turn marker; deterministic production turn."
        if "Configured fake directing decision marker" in intent:
            marker = (
                "Configured fake provider host turn marker; "
                "Configured fake directing decision marker; deterministic production turn."
            )
        return json.dumps(
            {
                "speaker_id": speaker_id,
                "text": marker,
                "evidence_ids": evidence_ids if isinstance(evidence_ids, list) else [],
            },
            sort_keys=True,
        )

    @staticmethod
    def _research_gap_response(request: LLMRequest) -> str:
        try:
            payload = json.loads(request.messages[-1].content)
        except (IndexError, json.JSONDecodeError):
            payload = {}
        sources = payload.get("sources", []) if isinstance(payload, dict) else []
        first_source = sources[0] if sources and isinstance(sources[0], dict) else {}
        source_id = str(first_source.get("source_id", ""))
        chunk_ids = first_source.get("chunk_ids", [])
        chunk_id = str(chunk_ids[0]) if chunk_ids else ""
        return json.dumps(
            {
                "gaps": [
                    {
                        "category": "missing_context",
                        "rationale": (
                            "Add corroborating context for the deterministic source corpus."
                        ),
                        "priority": 4,
                        "source_ids": [source_id] if source_id else [],
                        "chunk_ids": [chunk_id] if chunk_id else [],
                    }
                ]
            },
            sort_keys=True,
        )
