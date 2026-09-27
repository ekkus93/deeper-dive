"""Authoritative provider runtime ownership for a production session."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_factory import ProviderBuildResult
from deeper_dive.tts import TTSProvider, TTSProviderRegistry


@dataclass(slots=True)
class ProviderRuntime:
    """Own the current provider registries for one running application session."""

    _providers: ProviderBuildResult

    @property
    def providers(self) -> ProviderBuildResult:
        """Return the current complete provider build result."""

        return self._providers

    @property
    def llm_registry(self) -> LLMProviderRegistry:
        """Return the current LLM registry."""

        return self._providers.llm_registry

    @property
    def tts_registry(self) -> TTSProviderRegistry:
        """Return the current TTS registry."""

        return self._providers.tts_registry

    @property
    def tts_providers(self) -> dict[str, TTSProvider]:
        """Return the current concrete TTS provider map."""

        return self._providers.tts_providers

    def publish(self, providers: ProviderBuildResult) -> None:
        """Atomically publish a freshly built provider runtime."""

        self._providers = providers
