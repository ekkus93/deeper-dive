"""Construct runtime provider registries from persisted non-secret configuration."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from deeper_dive.elevenlabs_tts import ElevenLabsTTSProvider
from deeper_dive.kitten_tts import KittenTTSMicroProvider
from deeper_dive.llama_server_llm import LlamaServerLLMProvider
from deeper_dive.llm import (
    FakeLLMProvider,
    LLMModel,
    LLMProvider,
    LLMProviderRegistry,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    ProviderHealth,
)
from deeper_dive.ollama_llm import OllamaLLMProvider
from deeper_dive.openai_compatible_tts import OpenAICompatibleTTSProvider
from deeper_dive.openai_llm import OpenAILLMProvider
from deeper_dive.openai_tts import OpenAITTSProvider
from deeper_dive.tts import (
    FakeTTSProvider,
    TTSAudioResult,
    TTSProvider,
    TTSProviderRegistry,
    TTSRequest,
    TTSVoice,
)
from deeper_dive.user_config import ProviderConfig, UserConfig

LLM_PROVIDER_TYPES = frozenset({"fake", "openai", "ollama", "llama-server"})
TTS_PROVIDER_TYPES = frozenset(
    {
        "fake-tts",
        "kitten",
        "openai-tts",
        "openai-compatible-tts",
        "elevenlabs",
    }
)
LEGACY_PROVIDER_TYPES = frozenset({"llm", "tts"})


class ProviderConfigurationError(ValueError):
    """A persisted provider entry cannot be converted into a runtime adapter."""


@dataclass(frozen=True, slots=True)
class ProviderBuildResult:
    llm_registry: LLMProviderRegistry
    tts_registry: TTSProviderRegistry
    tts_providers: dict[str, TTSProvider]
    network_scopes: dict[str, str]


class _AliasedLLMProvider:
    def __init__(self, provider_id: str, delegate: LLMProvider) -> None:
        self._provider_id = provider_id
        self._delegate = delegate

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def health(self) -> ProviderHealth:
        return self._delegate.health()

    def models(self) -> tuple[LLMModel, ...]:
        return tuple(
            LLMModel(self.provider_id, model.model, model.capabilities)
            for model in self._delegate.models()
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        return self._delegate.generate(request)

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamChunk]:
        return self._delegate.stream(request)


class _AliasedTTSProvider:
    def __init__(self, provider_id: str, delegate: TTSProvider) -> None:
        self._provider_id = provider_id
        self._delegate = delegate

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def health(self) -> ProviderHealth:
        return self._delegate.health()

    def voices(self) -> tuple[TTSVoice, ...]:
        return self._delegate.voices()

    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        result = self._delegate.synthesize(request)
        return TTSAudioResult(
            audio=result.audio,
            media_type=result.media_type,
            format=result.format,
            provider=self.provider_id,
            voice=result.voice,
            model=result.model,
            sample_rate_hz=result.sample_rate_hz,
            duration_seconds=result.duration_seconds,
        )


class ProviderFactory:
    """Build configured provider adapters without persisting credentials."""

    def __init__(self, *, environ: Mapping[str, str] | None = None) -> None:
        self.environ = os.environ if environ is None else environ

    def build(self, config: UserConfig) -> ProviderBuildResult:
        llm_registry = LLMProviderRegistry()
        tts_registry = TTSProviderRegistry()
        tts_providers: dict[str, TTSProvider] = {}
        network_scopes: dict[str, str] = {}
        for name, provider_config in sorted(config.providers.items()):
            kind = self._normalized_type(provider_config.provider_type)
            network_scopes[name] = (
                provider_config.network_scope or self._default_network_scope(kind)
            )
            if kind in LLM_PROVIDER_TYPES:
                llm_registry.register(
                    _AliasedLLMProvider(
                        name,
                        self._llm(kind, provider_config),
                    )
                )
            elif kind in TTS_PROVIDER_TYPES:
                provider = _AliasedTTSProvider(
                    name,
                    self._tts(name, kind, provider_config),
                )
                tts_registry.register(provider)
                tts_providers[name] = provider
            else:
                raise ProviderConfigurationError(
                    f"provider {name!r} has unsupported provider_type "
                    f"{provider_config.provider_type!r}"
                )
        return ProviderBuildResult(
            llm_registry,
            tts_registry,
            tts_providers,
            network_scopes,
        )

    @staticmethod
    def _default_network_scope(kind: str) -> str:
        local_types = {"fake", "fake-tts", "kitten", "ollama", "llama-server"}
        return "local" if kind in local_types else "remote"

    @staticmethod
    def _normalized_type(value: str) -> str:
        normalized = value.strip().lower().replace("_", "-")
        if normalized in LEGACY_PROVIDER_TYPES:
            raise ProviderConfigurationError(
                f"legacy generic provider_type {value!r} is ambiguous; "
                "choose a concrete adapter type"
            )
        return normalized

    def _llm(self, kind: str, config: ProviderConfig) -> LLMProvider:
        model = self._model(config, kind)
        if kind == "fake":
            return FakeLLMProvider(model=model)
        if kind == "ollama":
            return OllamaLLMProvider(
                model=model,
                base_url=config.base_url or "http://127.0.0.1:11434",
                timeout=config.timeout_seconds,
            )
        if kind == "llama-server":
            return LlamaServerLLMProvider(
                model=model,
                base_url=config.base_url or "http://127.0.0.1:8080",
                timeout=config.timeout_seconds,
            )
        if kind == "openai":
            return OpenAILLMProvider(
                api_key=self._required_secret(config, "OPENAI_API_KEY", kind),
                model=model,
                base_url=config.base_url or "https://api.openai.com/v1",
                timeout=config.timeout_seconds,
            )
        raise ProviderConfigurationError(f"unsupported LLM provider type: {kind}")

    def _tts(
        self,
        name: str,
        kind: str,
        config: ProviderConfig,
    ) -> TTSProvider:
        if kind == "fake-tts":
            return FakeTTSProvider(provider_id=name)
        if kind == "kitten":
            return KittenTTSMicroProvider()
        if kind == "openai-tts":
            return OpenAITTSProvider(
                api_key=self._required_secret(config, "OPENAI_API_KEY", kind),
                model=config.default_model or "gpt-4o-mini-tts",
                base_url=config.base_url or "https://api.openai.com/v1",
                timeout=config.timeout_seconds,
            )
        if kind == "elevenlabs":
            return ElevenLabsTTSProvider(
                api_key=self._required_secret(config, "ELEVENLABS_API_KEY", kind),
                model=config.default_model or "eleven_multilingual_v2",
                base_url=config.base_url or "https://api.elevenlabs.io/v1",
                timeout=config.timeout_seconds,
            )
        if kind == "openai-compatible-tts":
            if not config.base_url:
                raise ProviderConfigurationError(
                    f"provider {name!r} requires base_url for openai-compatible-tts"
                )
            voices = tuple(config.voices)
            if not voices:
                raise ProviderConfigurationError(
                    f"provider {name!r} requires at least one configured voice"
                )
            return OpenAICompatibleTTSProvider(
                provider_id=name,
                base_url=config.base_url,
                model=config.default_model or "tts-1",
                voices=voices,
                api_key=self._optional_secret(config),
                response_format=config.response_format,
                timeout=config.timeout_seconds,
            )
        raise ProviderConfigurationError(f"unsupported TTS provider type: {kind}")

    @staticmethod
    def _model(config: ProviderConfig, kind: str) -> str:
        if config.default_model:
            return config.default_model
        if kind == "fake":
            return "fake-v1"
        raise ProviderConfigurationError(f"provider type {kind!r} requires default_model")

    def _optional_secret(self, config: ProviderConfig) -> str | None:
        if not config.credential_env:
            return None
        return self.environ.get(config.credential_env)

    def _required_secret(
        self,
        config: ProviderConfig,
        fallback_env: str,
        kind: str,
    ) -> str:
        env_name = config.credential_env or fallback_env
        secret = self.environ.get(env_name)
        if not secret:
            raise ProviderConfigurationError(
                f"provider type {kind!r} requires credential environment variable {env_name}"
            )
        return secret
