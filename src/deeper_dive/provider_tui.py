"""Provider configuration support for the Textual interface."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from deeper_dive.llm import LLMProvider, LLMProviderRegistry
from deeper_dive.model_roles import ModelRole
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
    "fake-tts": frozenset({"network_scope", "voices"}),
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
    on_reload: Callable[[ProviderBuildResult], None] | None = None

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
        fields = _PROVIDER_CONFIGURATION_FIELDS.get(kind)
        if fields is None:
            # Adapter type is user input: never echo it in CLI/TUI errors.
            raise ValueError("unsupported provider adapter")
        return fields

    def validate_default_references(self, config: UserConfig) -> None:
        """Reject impossible provider references without performing live discovery."""

        for role in ModelRole:
            identity = config.defaults.get(role.value, "").strip()
            if not identity or ":" not in identity:
                # Legacy bare model IDs are preserved on load and may be migrated
                # later, but newly written invalid syntax is rejected by UserConfig.
                continue
            provider_id, _model = identity.split(":", 1)
            referenced = config.providers.get(provider_id)
            if referenced is None:
                raise ValueError(f"{role.value} references an unknown provider")
            if self.capability(referenced.provider_type) != "llm":
                raise ValueError(f"{role.value} must reference a language-model provider")

        tts_provider = config.defaults.get("tts_provider", "").strip()
        if tts_provider:
            referenced = config.providers.get(tts_provider)
            if referenced is None:
                raise ValueError("tts_provider references an unknown provider")
            if self.capability(referenced.provider_type) != "tts":
                raise ValueError("tts_provider must reference a speech provider")
            # Explicitly configured provider voices are authoritative without
            # making a network discovery call during Settings or first-run saves.
            # Providers with no declared voices may discover them at runtime.
            if referenced.voices:
                for key in ("tts_voice", "tts_voice_host_1", "tts_voice_host_2"):
                    voice = config.defaults.get(key, "").strip()
                    if voice and voice not in referenced.voices:
                        raise ValueError(f"{key} references a voice not declared by tts_provider")

        local_ids = tuple(
            item.strip()
            for item in config.defaults.get("local_provider_ids", "").split(",")
            if item.strip()
        )
        if any(provider_id not in config.providers for provider_id in local_ids):
            raise ValueError("local_provider_ids contains an unknown provider")

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
        default_updates: Mapping[str, str] | None = None,
    ) -> None:
        # Reject raw control characters before strip/lower can conceal them.
        if any(ord(character) < 32 or ord(character) == 127 for character in provider_type):
            raise ValueError("provider_type must be a single-line adapter identifier")
        kind = provider_type.strip().lower().replace("_", "-")
        if self.capability(kind) == "unknown":
            supported = ", ".join(sorted(LLM_PROVIDER_TYPES | TTS_PROVIDER_TYPES))
            raise ValueError(f"unsupported provider adapter; choose one of: {supported}")
        candidate = self.config().model_copy(deep=True)
        candidate.providers[name] = ProviderConfig(
            provider_type=kind,
            base_url=base_url or None,
            default_model=default_model or None,
            credential_env=credential_env or None,
            timeout_seconds=timeout_seconds,
            network_scope=network_scope,  # type: ignore[arg-type]
            response_format=response_format,
            voices=voices,
        )
        for key, value in (default_updates or {}).items():
            name_key = key.strip()
            if not name_key:
                raise ValueError("settings key is required")
            # The provider-composite path must not strip control bytes before
            # the shared durable validation sees the caller's original value.
            if any(ord(character) < 32 or ord(character) == 127 for character in key + value):
                raise ValueError("settings keys and values must be single-line")
            normalized = value.strip()
            if normalized:
                candidate.defaults[name_key] = normalized
            else:
                candidate.defaults.pop(name_key, None)
        self._commit_candidate(candidate)

    def remove_provider(self, name: str) -> None:
        candidate = self.config().model_copy(deep=True)
        candidate.providers.pop(name, None)
        # Deleting a provider intentionally leaves old assignments unresolved;
        # the shared preflight must block until they are reconfigured.
        self._commit_candidate(candidate, allow_unresolved_references=True)

    def _commit_candidate(
        self, candidate: UserConfig, *, allow_unresolved_references: bool = False
    ) -> ProviderBuildResult | None:
        """Build first, persist second, and publish only a fully durable runtime."""

        validated = self.config_store.validate_candidate(candidate)
        if not allow_unresolved_references:
            self.validate_default_references(validated)
        if self.provider_factory is None:
            self.config_store.save(candidate)
            return None
        providers = self.provider_factory.build(validated)
        self.config_store.save(candidate)
        self._publish(providers)
        return providers

    def _publish(self, providers: ProviderBuildResult) -> None:
        self.llm_registry = providers.llm_registry
        self.tts_providers = providers.tts_providers
        if self.on_reload is not None:
            self.on_reload(providers)

    def reload(self) -> ProviderBuildResult | None:
        if self.provider_factory is None:
            return None
        providers = self.provider_factory.build(self.config())
        self._publish(providers)
        return providers

    def readiness_probe_controller(
        self, *, request_timeout_seconds: float = 1.0
    ) -> ProviderController:
        """Use isolated, bounded I/O adapters for UI readiness only.

        Never mutate live generation provider timeouts or published registries.
        Custom/injected factories retain their existing deterministic test boundary.
        """
        if self.provider_factory is None or type(self.provider_factory) is not ProviderFactory:
            return self
        configured = self.config()
        isolated = self.provider_factory.build(
            configured, probe_timeout_seconds=request_timeout_seconds
        )
        return ProviderController(
            self.config_store,
            isolated.llm_registry,
            isolated.tts_providers,
        )

    def llm(self, name: str) -> LLMProvider:
        return self.llm_registry.get(name)

    def tts(self, name: str) -> TTSProvider:
        try:
            return self.tts_providers[name]
        except KeyError:
            raise KeyError("unknown TTS provider") from None

    def health(self, name: str) -> object:
        """Route UI health checks through the configured runtime adapter."""

        config = self.config().providers.get(name)
        if config is None:
            raise KeyError("unknown provider") from None
        capability = self.capability(config.provider_type)
        if capability == "llm":
            return self.llm(name).health()
        if capability == "tts":
            return self.tts(name).health()
        raise ValueError("unsupported provider adapter")
