from __future__ import annotations

import pytest

from deeper_dive.provider_factory import ProviderConfigurationError, ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig


def test_factory_registers_configured_names_for_deterministic_providers() -> None:
    result = ProviderFactory(environ={}).build(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v2"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            }
        )
    )

    assert result.llm_registry.provider_ids() == ("planner",)
    assert result.llm_registry.get("planner").models()[0].provider == "planner"
    assert result.llm_registry.get("planner").models()[0].model == "fake-v2"
    assert result.tts_registry.provider_ids() == ("speech",)
    assert result.tts_providers["speech"].provider_id == "speech"


def test_factory_builds_local_llm_adapters_without_contacting_network() -> None:
    result = ProviderFactory(environ={}).build(
        UserConfig(
            providers={
                "local": ProviderConfig(
                    provider_type="ollama",
                    base_url="http://127.0.0.1:11434",
                    default_model="qwen3",
                ),
                "llama": ProviderConfig(
                    provider_type="llama_server",
                    base_url="http://127.0.0.1:8080",
                    default_model="local.gguf",
                ),
            }
        )
    )

    assert result.llm_registry.provider_ids() == ("llama", "local")
    assert result.llm_registry.get("local").provider_id == "local"
    assert result.llm_registry.get("llama").provider_id == "llama"


def test_factory_builds_every_remote_adapter_without_network_calls() -> None:
    result = ProviderFactory(
        environ={
            "OPENAI_API_KEY": "openai-fixture-secret",
            "ELEVENLABS_API_KEY": "eleven-fixture-secret",
            "COMPAT_KEY": "compat-fixture-secret",
        }
    ).build(
        UserConfig(
            providers={
                "openai-chat": ProviderConfig(
                    provider_type="openai",
                    default_model="gpt-test",
                ),
                "openai-speech": ProviderConfig(provider_type="openai-tts"),
                "eleven-speech": ProviderConfig(provider_type="elevenlabs"),
                "compatible-speech": ProviderConfig(
                    provider_type="openai-compatible-tts",
                    base_url="https://tts.example.invalid/v1",
                    credential_env="COMPAT_KEY",
                    voices=("voice-a",),
                ),
            }
        )
    )

    assert result.llm_registry.provider_ids() == ("openai-chat",)
    assert result.tts_registry.provider_ids() == (
        "compatible-speech",
        "eleven-speech",
        "openai-speech",
    )
    assert result.network_scopes == {
        "compatible-speech": "remote",
        "eleven-speech": "remote",
        "openai-chat": "remote",
        "openai-speech": "remote",
    }


def test_factory_builds_kitten_adapter_without_loading_model() -> None:
    result = ProviderFactory(environ={}).build(
        UserConfig(providers={"local-speech": ProviderConfig(provider_type="kitten")})
    )

    assert result.tts_registry.provider_ids() == ("local-speech",)
    assert result.tts_providers["local-speech"].provider_id == "local-speech"
    assert result.network_scopes["local-speech"] == "local"


def test_factory_preserves_effective_network_policy_metadata() -> None:
    result = ProviderFactory(environ={"OPENAI_API_KEY": "fixture"}).build(
        UserConfig(
            providers={
                "local": ProviderConfig(provider_type="fake"),
                "cloud": ProviderConfig(
                    provider_type="openai",
                    default_model="gpt-test",
                ),
                "forced-local": ProviderConfig(
                    provider_type="openai",
                    default_model="gpt-test",
                    network_scope="local",
                ),
            }
        )
    )

    assert result.network_scopes == {
        "cloud": "remote",
        "forced-local": "local",
        "local": "local",
    }


def test_factory_requires_cloud_credential_only_when_provider_is_configured() -> None:
    with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
        ProviderFactory(environ={}).build(
            UserConfig(
                providers={
                    "cloud": ProviderConfig(
                        provider_type="openai",
                        default_model="gpt-test",
                    )
                }
            )
        )


def test_factory_uses_explicit_credential_environment_reference() -> None:
    result = ProviderFactory(environ={"DD_OPENAI_KEY": "fixture-value"}).build(
        UserConfig(
            providers={
                "cloud": ProviderConfig(
                    provider_type="openai",
                    default_model="gpt-test",
                    credential_env="DD_OPENAI_KEY",
                )
            }
        )
    )
    assert result.llm_registry.provider_ids() == ("cloud",)


def test_factory_rejects_ambiguous_legacy_generic_types() -> None:
    with pytest.raises(ProviderConfigurationError, match="ambiguous"):
        ProviderFactory(environ={}).build(
            UserConfig(providers={"legacy": ProviderConfig(provider_type="llm")})
        )


def test_factory_configuration_errors_never_echo_secret_values() -> None:
    secret = "do-not-echo-this-secret"
    config = UserConfig(
        providers={
            "broken": ProviderConfig(
                provider_type="openai-compatible-tts",
                credential_env="COMPAT_KEY",
            )
        }
    )

    with pytest.raises(ProviderConfigurationError) as captured:
        ProviderFactory(environ={"COMPAT_KEY": secret}).build(config)

    message = str(captured.value)
    assert "base_url" in message
    assert secret not in message
