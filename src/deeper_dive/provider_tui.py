"""Provider configuration support for the Textual interface."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.llm import LLMProvider, LLMProviderRegistry
from deeper_dive.provider_factory import (
    LLM_PROVIDER_TYPES,
    TTS_PROVIDER_TYPES,
    ProviderBuildResult,
    ProviderFactory,
)
from deeper_dive.tts import TTSProvider
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


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

    def save_provider(
        self,
        name: str,
        provider_type: str,
        *,
        base_url: str | None = None,
        default_model: str | None = None,
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
        )
        providers = self._build(config)
        self.config_store.save(config)
        self._install(providers)

    def remove_provider(self, name: str) -> None:
        config = self.config()
        config.providers.pop(name, None)
        providers = self._build(config)
        self.config_store.save(config)
        self._install(providers)

    def reload(self) -> ProviderBuildResult | None:
        providers = self._build(self.config())
        self._install(providers)
        return providers

    def _build(self, config: UserConfig) -> ProviderBuildResult | None:
        if self.provider_factory is None:
            return None
        return self.provider_factory.build(config)

    def _install(self, providers: ProviderBuildResult | None) -> None:
        if providers is None:
            return
        self.llm_registry = providers.llm_registry
        self.tts_providers = providers.tts_providers

    def llm(self, name: str) -> LLMProvider:
        return self.llm_registry.get(name)

    def tts(self, name: str) -> TTSProvider:
        try:
            return self.tts_providers[name]
        except KeyError as exc:
            raise KeyError(f"unknown TTS provider: {name}") from exc
