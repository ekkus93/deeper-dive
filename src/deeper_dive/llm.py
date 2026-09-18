"""Normalized LLM provider contract, registry, and deterministic fake provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Mapping, Protocol


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
        return {provider_id: self._providers[provider_id].health() for provider_id in self.provider_ids()}

    def models(self) -> dict[str, tuple[LLMModel, ...]]:
        return {provider_id: self._providers[provider_id].models() for provider_id in self.provider_ids()}


class FakeLLMProvider:
    """Deterministic provider for orchestration and integration tests."""

    def __init__(self, *, provider_id: str = "fake", model: str = "fake-v1", response: str = "fake response") -> None:
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
        input_tokens = sum(len(message.content.split()) for message in request.messages)
        output_tokens = len(self.response.split())
        return LLMResponse(self.response, model, LLMUsage(input_tokens, output_tokens))

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        self.requests.append(request)
        words = self.response.split()
        for index, word in enumerate(words):
            suffix = "" if index == len(words) - 1 else " "
            yield LLMStreamChunk(word + suffix, done=index == len(words) - 1)
