from __future__ import annotations

import pytest

from deeper_dive.network_scope import ProviderNetworkPolicy
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig


@pytest.mark.parametrize(
    ("provider_type", "expected"),
    [
        ("fake", "local"),
        ("fake-tts", "local"),
        ("kitten", "local"),
        ("ollama", "local"),
        ("llama-server", "local"),
        ("openai", "remote"),
        ("openai-tts", "remote"),
        ("openai-compatible-tts", "remote"),
        ("elevenlabs", "remote"),
    ],
)
def test_provider_network_policy_default_scope_matrix(
    provider_type: str,
    expected: str,
) -> None:
    assert ProviderNetworkPolicy.default_scope_for_type(provider_type) == expected


@pytest.mark.parametrize("scope", ["local", "remote"])
def test_explicit_network_scope_overrides_adapter_default(scope: str) -> None:
    local_config = ProviderConfig(provider_type="openai", network_scope=scope)
    remote_config = ProviderConfig(provider_type="fake", network_scope=scope)

    assert ProviderNetworkPolicy.scope_for_config(local_config) == scope
    assert ProviderNetworkPolicy.scope_for_config(remote_config) == scope


def test_local_provider_ids_respect_defaults_and_explicit_remote_override() -> None:
    config = UserConfig(
        defaults={"local_provider_ids": "cloud, manual", "local_only": "YES"},
        providers={
            "cloud": ProviderConfig(provider_type="openai", network_scope="remote"),
            "explicit_local": ProviderConfig(provider_type="openai", network_scope="local"),
            "fake_local": ProviderConfig(provider_type="fake"),
            "remote_tts": ProviderConfig(provider_type="openai-tts"),
        },
    )

    assert ProviderNetworkPolicy.local_provider_ids(config) == frozenset(
        {"manual", "explicit_local", "fake_local"}
    )
    assert ProviderNetworkPolicy.local_only(config.defaults)


def test_provider_factory_uses_shared_network_scope_policy() -> None:
    config = UserConfig(
        providers={
            "fake": ProviderConfig(provider_type="fake"),
            "remote_fake": ProviderConfig(provider_type="fake", network_scope="remote"),
            "local_cloud": ProviderConfig(
                provider_type="openai",
                default_model="gpt-test",
                network_scope="local",
            ),
        }
    )

    result = ProviderFactory(environ={"OPENAI_API_KEY": "test-key"}).build(config)

    assert result.network_scopes == {
        "fake": "local",
        "local_cloud": "local",
        "remote_fake": "remote",
    }
