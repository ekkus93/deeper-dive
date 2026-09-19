"""Provider configuration support for the Textual interface."""

from __future__ import annotations

from dataclasses import dataclass
from deeper_dive.llm import LLMProvider, LLMProviderRegistry
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore

from deeper_dive.tts import TTSProvider


@dataclass(slots=True)
class ProviderController:
    config_store: UserConfigStore
    llm_registry: LLMProviderRegistry
    tts_providers: dict[str, TTSProvider]

    def config(self) -> UserConfig:
        return self.config_store.load()

    def save_provider(
        self,
        name: str,
        provider_type: str,
        *,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> None:
        config = self.config()
        config.providers[name] = ProviderConfig(
            provider_type=provider_type,
            base_url=base_url or None,
            default_model=default_model or None,
        )
        self.config_store.save(config)

    def remove_provider(self, name: str) -> None:
        config = self.config()
        config.providers.pop(name, None)
        self.config_store.save(config)

    def llm(self, name: str) -> LLMProvider:
        return self.llm_registry.get(name)

    def tts(self, name: str) -> TTSProvider:
        try:
            return self.tts_providers[name]
        except KeyError as exc:
            raise KeyError(f"unknown TTS provider: {name}") from exc
