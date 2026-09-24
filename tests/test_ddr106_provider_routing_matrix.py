from __future__ import annotations

import pytest

from deeper_dive.provider_factory import ProviderConfigurationError, ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig


def test_provider_routing_matrix_constructs_every_supported_route_without_network() -> None:
    factory = ProviderFactory(
        environ={
            "OPENAI_API_KEY": "fixture-openai",
            "ELEVENLABS_API_KEY": "fixture-eleven",
            "COMPAT_KEY": "fixture-compat",
        }
    )
    result = factory.build(
        UserConfig(
            providers={
                "openai": ProviderConfig(provider_type="openai", default_model="gpt-test"),
                "ollama": ProviderConfig(
                    provider_type="ollama",
                    base_url="http://127.0.0.1:11434",
                    default_model="qwen-test",
                ),
                "llama": ProviderConfig(
                    provider_type="llama_server",
                    base_url="http://127.0.0.1:8080",
                    default_model="local.gguf",
                ),
                "kitten": ProviderConfig(provider_type="kitten"),
                "openai-tts": ProviderConfig(provider_type="openai-tts"),
                "compatible-tts": ProviderConfig(
                    provider_type="openai-compatible-tts",
                    base_url="https://tts.example.invalid/v1",
                    credential_env="COMPAT_KEY",
                    voices=("voice-a",),
                ),
                "eleven": ProviderConfig(provider_type="elevenlabs"),
            }
        )
    )

    assert result.llm_registry.provider_ids() == ("llama", "ollama", "openai")
    assert result.tts_registry.provider_ids() == (
        "compatible-tts",
        "eleven",
        "kitten",
        "openai-tts",
    )
    assert result.network_scopes == {
        "compatible-tts": "remote",
        "eleven": "remote",
        "kitten": "local",
        "llama": "local",
        "ollama": "local",
        "openai": "remote",
        "openai-tts": "remote",
    }


def test_provider_routing_matrix_fails_closed_without_required_credentials() -> None:
    with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
        ProviderFactory(environ={}).build(
            UserConfig(
                providers={
                    "openai": ProviderConfig(
                        provider_type="openai",
                        default_model="gpt-test",
                    )
                }
            )
        )


def test_provider_routing_matrix_rejects_unknown_provider_type() -> None:
    with pytest.raises(ProviderConfigurationError, match="unsupported provider_type"):
        ProviderFactory(environ={}).build(
            UserConfig(providers={"unknown": ProviderConfig(provider_type="not-a-provider")})
        )
