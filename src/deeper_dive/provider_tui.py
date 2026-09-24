"""Provider configuration support for the Textual interface."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.llm import (
    LLMProvider,
    LLMProviderRegistry,
    ProviderHealth,
)
from deeper_dive.provider_factory import (
    LLM_PROVIDER_TYPES,
    TTS_PROVIDER_TYPES,
    ProviderBuildResult,
    ProviderFactory,
)
from deeper_dive.tts import TTSProvider
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


_PROVIDER_CONFIGURATION_FIELDS: dict[str, frozenset[str]] = {
    "fake": frozenset({"default_model", "network_scope"}),
    "openai": frozenset(
        {
            "base_url",
            "default_model",
            "credential_env",
            "timeout_seconds",
            "network_scope",
        }
    ),
    "ollama": frozenset({"base_url", "default_model", "timeout_seconds", "network_scope"}),
    "llama-server": frozenset({"base_url", "default_model", "timeout_seconds", "network_scope"}),
    "fake-tts": frozenset({"network_scope"}),
    "kitten": frozenset({"network_scope"}),
    "openai-tts": frozenset(
        {
            "base_url",
            "default_model",
            "credential_env",
            "timeout_seconds",
            "network_scope",
        }
    ),
    "openai-compatible-tts": frozenset(
        {
            "base_url",
            "default_model",
            "credential_env",
            "timeout_seconds",
            "network_scope",
            "response_format",
            "voices",
        }
    ),
    "elevenlabs": frozenset(
        {
            "base_url",
            "default_model",
            "credential_env",
            "timeout_seconds",
            "network_scope",
        }
    ),
}


@dataclass(slots=True)
class ProviderController:
    config_store: UserConfigStore
    llm_registry: LLMProviderRegistry
    tts_providers: dict[str, TTSProvider]
    provider_factory: ProviderFactory | None = None

    def config(self) -> UserConfig:
        return self.config_store.load()

    @staticmethod
    def capability(provider_type: str) -> str:
        kind = provider_type.strip().lower().replace("_", "-")
        if kind in LLM_PROVIDER_TYPES:
            return "llm"
        if kind in TTS_PROVIDER_TYPES:
            return "tts"
        return "unknown"

    @staticmethod
    def configuration_fields(provider_type: str) -> frozenset[str]:
        """Return fields the UI should expose for one concrete adapter type."""

        kind = provider_type.strip().lower().replace("_", "-")
        try:
            return _PROVIDER_CONFIGURATION_FIELDS[kind]
        except KeyError as exc:
            raise ValueError(f"unsupported provider adapter {provider_type!r}") from exc

    def save_provider(
        self,
        name: str,
        provider_type: str,
        *,
        base_url: str | None = None,
        default_model: str | None = None,
        credential_env: str | None = None,
        timeout_seconds: float = 60.0,
        network_scope: str | None = None,
        response_format: str = "wav",
        voices: tuple[str, ...] = (),
    ) -> None:
        kind = provider_type.strip().lower().replace("_", "-")
        if self.capability(kind) == "unknown":
            supported = ", ".join(sorted(LLM_PROVIDER_TYPES | TTS_PROVIDER_TYPES))
            raise ValueError(
                f"unsupported provider adapter {provider_type!r}; choose one of: {supported}"
            )
        config = self.config()
        config.providers[name] = ProviderConfig(
            provider_type=kind,
            base_url=base_url or None,
            default_model=default_model or None,
            credential_env=credential_env or None,
            timeout_seconds=timeout_seconds,
            network_scope=network_scope,  # type: ignore[arg-type]
            response_format=response_format,
            voices=voices,
        )
        self.config_store.save(config)
        self.reload()

    def remove_provider(self, name: str) -> None:
        config = self.config()
        config.providers.pop(name, None)
        self.config_store.save(config)
        self.reload()

    def reload(self) -> ProviderBuildResult | None:
        if self.provider_factory is None:
            return None
        providers = self.provider_factory.build(self.config())
        self.llm_registry = providers.llm_registry
        self.tts_providers = providers.tts_providers
        return providers

    def llm(self, name: str) -> LLMProvider:
        return self.llm_registry.get(name)

    def tts(self, name: str) -> TTSProvider:
        try:
            return self.tts_providers[name]
        except KeyError as exc:
            raise KeyError(f"unknown TTS provider: {name}") from exc

    def health(self, name: str) -> ProviderHealth:
        """Route UI health checks through the configured runtime adapter."""

        config = self.config().providers.get(name)
        if config is None:
            raise KeyError(f"unknown provider: {name}")
        capability = self.capability(config.provider_type)
        if capability == "llm":
            return self.llm(name).health()
        if capability == "tts":
            return self.tts(name).health()
        raise ValueError(f"unsupported provider adapter {config.provider_type!r}")
