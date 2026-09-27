from __future__ import annotations

import pytest

from deeper_dive.provider_network import (
    LOCAL_PROVIDER_TYPES,
    local_only_from_defaults,
    local_provider_ids,
    provider_is_local,
)
from deeper_dive.user_config import ProviderConfig


@pytest.mark.parametrize("provider_type", sorted(LOCAL_PROVIDER_TYPES))
def test_known_local_provider_types_are_local(provider_type: str) -> None:
    provider = ProviderConfig(provider_type=provider_type)

    assert provider_is_local("provider", provider, {})
    assert local_provider_ids({"provider": provider}, {}) == frozenset({"provider"})


@pytest.mark.parametrize(
    "provider_type",
    [
        "openai",
        "openai-tts",
        "openai-compatible-tts",
        "elevenlabs",
    ],
)
def test_remote_provider_types_are_remote_by_default(provider_type: str) -> None:
    providers = {"remote": ProviderConfig(provider_type=provider_type)}

    assert local_provider_ids(providers, {}) == frozenset()


def test_explicit_local_scope_overrides_remote_provider_type() -> None:
    providers = {
        "remote": ProviderConfig(provider_type="openai", network_scope="local"),
    }

    assert local_provider_ids(providers, {}) == frozenset({"remote"})


def test_explicit_remote_scope_overrides_local_provider_type_and_legacy_default() -> None:
    providers = {
        "fake": ProviderConfig(provider_type="fake", network_scope="remote"),
    }

    assert local_provider_ids(providers, {"local_provider_ids": "fake"}) == frozenset()


def test_legacy_local_provider_ids_still_work_when_scope_is_unspecified() -> None:
    providers = {
        "remote": ProviderConfig(provider_type="openai"),
        "other": ProviderConfig(provider_type="openai"),
    }

    assert local_provider_ids(
        providers,
        {"local_provider_ids": " remote , missing "},
    ) == frozenset({"missing", "remote"})


def test_legacy_local_provider_ids_cover_runtime_only_providers() -> None:
    assert local_provider_ids({}, {"local_provider_ids": "fake-tts"}) == frozenset(
        {"fake-tts"}
    )


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_local_only_defaults_accept_common_true_values(value: str) -> None:
    assert local_only_from_defaults({"local_only": value})


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_local_only_defaults_reject_false_values(value: str) -> None:
    assert not local_only_from_defaults({"local_only": value})
