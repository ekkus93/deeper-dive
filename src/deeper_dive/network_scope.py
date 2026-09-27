"""Shared provider locality and network-scope policy."""

from __future__ import annotations

from deeper_dive.user_config import ProviderConfig, UserConfig


class ProviderNetworkPolicy:
    """Classify provider routes consistently across CLI, TUI, and preflight."""

    LOCAL_PROVIDER_TYPES = frozenset(
        {"fake", "fake-tts", "kitten", "ollama", "llama-server"}
    )
    TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

    @classmethod
    def normalize_provider_type(cls, provider_type: str) -> str:
        """Normalize a persisted adapter name before locality classification."""

        return provider_type.strip().lower().replace("_", "-")

    @classmethod
    def default_scope_for_type(cls, provider_type: str) -> str:
        """Return the inferred scope for an adapter type when no override exists."""

        kind = cls.normalize_provider_type(provider_type)
        return "local" if kind in cls.LOCAL_PROVIDER_TYPES else "remote"

    @classmethod
    def scope_for_config(cls, config: ProviderConfig) -> str:
        """Return explicit provider network_scope or the adapter default."""

        if config.network_scope is not None:
            return config.network_scope
        return cls.default_scope_for_type(config.provider_type)

    @classmethod
    def local_provider_ids(cls, config: UserConfig) -> frozenset[str]:
        """Return providers considered local for content-routing disclosure.

        Legacy user defaults may name additional local providers, but an explicit
        per-provider network_scope always wins over both defaults and adapter
        inference.
        """

        local_ids = {
            value.strip()
            for value in config.defaults.get("local_provider_ids", "").split(",")
            if value.strip()
        }
        for name, provider in config.providers.items():
            if provider.network_scope == "local":
                local_ids.add(name)
            elif provider.network_scope == "remote":
                local_ids.discard(name)
            elif cls.default_scope_for_type(provider.provider_type) == "local":
                local_ids.add(name)
        return frozenset(local_ids)

    @classmethod
    def local_only(cls, defaults: dict[str, str]) -> bool:
        """Return whether generation must reject remote provider routes."""

        return defaults.get("local_only", "").strip().lower() in cls.TRUE_VALUES
