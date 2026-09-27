"""Shared local/remote provider classification policy."""

from __future__ import annotations

from collections.abc import Mapping

from deeper_dive.user_config import ProviderConfig

LOCAL_PROVIDER_TYPES = frozenset(
    {
        "fake",
        "fake-tts",
        "kitten",
        "llama-server",
        "local",
        "ollama",
    }
)
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def normalize_provider_type(provider_type: str) -> str:
    """Normalize provider type spelling before local/remote classification."""

    return provider_type.strip().lower().replace("_", "-")


def local_only_from_defaults(defaults: Mapping[str, str]) -> bool:
    """Return whether project/user defaults request a hard local-only route."""

    return defaults.get("local_only", "").strip().lower() in _TRUE_VALUES


def configured_local_provider_ids(defaults: Mapping[str, str]) -> set[str]:
    """Parse the legacy comma-delimited explicit local provider list."""

    return {
        value.strip()
        for value in defaults.get("local_provider_ids", "").split(",")
        if value.strip()
    }


def provider_is_local(
    provider_id: str,
    provider: ProviderConfig,
    defaults: Mapping[str, str],
) -> bool:
    """Classify one provider using explicit scope before defaults and adapter type."""

    scope = (provider.network_scope or "").strip().lower()
    if scope == "local":
        return True
    if scope == "remote":
        return False
    if provider_id in configured_local_provider_ids(defaults):
        return True
    return normalize_provider_type(provider.provider_type) in LOCAL_PROVIDER_TYPES


def local_provider_ids(
    providers: Mapping[str, ProviderConfig], defaults: Mapping[str, str]
) -> frozenset[str]:
    """Return provider ids considered local by the shared network-scope policy."""

    local_ids = configured_local_provider_ids(defaults)
    for provider_id, provider in providers.items():
        scope = (provider.network_scope or "").strip().lower()
        if scope == "remote":
            local_ids.discard(provider_id)
        elif provider_is_local(provider_id, provider, defaults):
            local_ids.add(provider_id)
    return frozenset(local_ids)
