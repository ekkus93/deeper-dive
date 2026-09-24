from __future__ import annotations

import pytest

from deeper_dive.llm import LLMProviderRegistry, ProviderHealth
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import UserConfigStore


def _controller(tmp_path, *, environ: dict[str, str] | None = None) -> ProviderController:
    return ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={} if environ is None else environ),
    )


def test_save_concrete_adapter_reloads_runtime_registry(tmp_path) -> None:
    controller = _controller(tmp_path)

    controller.save_provider("planner", "fake", default_model="fake-v2")

    assert controller.config().providers["planner"].provider_type == "fake"
    assert controller.capability("fake") == "llm"
    assert controller.llm("planner").models()[0].model == "fake-v2"


def test_edit_concrete_adapter_reloads_updated_runtime_registry(tmp_path) -> None:
    controller = _controller(tmp_path)
    controller.save_provider("planner", "fake", default_model="fake-v1")

    controller.save_provider("planner", "fake", default_model="fake-v2")

    assert controller.config().providers["planner"].default_model == "fake-v2"
    assert controller.llm("planner").models()[0].model == "fake-v2"


def test_save_tts_adapter_reloads_runtime_provider(tmp_path) -> None:
    controller = _controller(tmp_path)

    controller.save_provider("speech", "fake_tts")

    assert controller.config().providers["speech"].provider_type == "fake-tts"
    assert controller.capability("fake-tts") == "tts"
    assert controller.tts("speech").provider_id == "speech"


def test_save_provider_persists_extended_configuration_fields(tmp_path) -> None:
    controller = _controller(tmp_path)

    controller.save_provider(
        "speech",
        "openai-compatible-tts",
        base_url="http://127.0.0.1:9000/v1",
        default_model="local-tts",
        credential_env="LOCAL_TTS_TOKEN",
        timeout_seconds=12.5,
        network_scope="local",
        response_format="mp3",
        voices=("alice", "bob"),
    )

    saved = controller.config().providers["speech"]
    assert saved.credential_env == "LOCAL_TTS_TOKEN"
    assert saved.timeout_seconds == 12.5
    assert saved.network_scope == "local"
    assert saved.response_format == "mp3"
    assert saved.voices == ("alice", "bob")
    assert tuple(voice.id for voice in controller.tts("speech").voices()) == (
        "alice",
        "bob",
    )


def test_save_provider_validates_extended_configuration_fields(tmp_path) -> None:
    controller = _controller(tmp_path)

    with pytest.raises(ValueError, match="timeout_seconds"):
        controller.save_provider("planner", "fake", timeout_seconds=0)
    with pytest.raises(ValueError, match="network_scope"):
        controller.save_provider("planner", "fake", network_scope="internet")

    assert "planner" not in controller.config().providers


@pytest.mark.parametrize(
    ("name", "provider_type", "kwargs", "capability"),
    (
        (
            "openai-main",
            "openai",
            {"default_model": "gpt-test", "credential_env": "OPENAI_TEST_KEY"},
            "llm",
        ),
        (
            "ollama-local",
            "ollama",
            {"default_model": "qwen-test", "base_url": "http://127.0.0.1:11434"},
            "llm",
        ),
        (
            "compatible-local",
            "llama-server",
            {"default_model": "local-test", "base_url": "http://127.0.0.1:8080"},
            "llm",
        ),
        ("kitten-local", "kitten", {}, "tts"),
        (
            "openai-speech",
            "openai-tts",
            {"default_model": "tts-test", "credential_env": "OPENAI_TEST_KEY"},
            "tts",
        ),
        (
            "compatible-speech",
            "openai-compatible-tts",
            {
                "base_url": "http://127.0.0.1:9000/v1",
                "default_model": "local-tts",
                "voices": ("voice-a",),
                "credential_env": "LOCAL_TTS_KEY",
            },
            "tts",
        ),
        (
            "eleven-speech",
            "elevenlabs",
            {"default_model": "eleven-test", "credential_env": "ELEVEN_TEST_KEY"},
            "tts",
        ),
    ),
)
def test_supported_adapter_classes_save_reload_and_health_through_controller(
    tmp_path,
    monkeypatch,
    name: str,
    provider_type: str,
    kwargs: dict[str, object],
    capability: str,
) -> None:
    secrets = {
        "OPENAI_TEST_KEY": "openai-secret-value",
        "LOCAL_TTS_KEY": "local-secret-value",
        "ELEVEN_TEST_KEY": "eleven-secret-value",
    }
    controller = _controller(tmp_path, environ=secrets)

    controller.save_provider(name, provider_type, **kwargs)  # type: ignore[arg-type]
    reloaded = controller.reload()

    assert reloaded is not None
    saved = controller.config().providers[name]
    assert saved.provider_type == provider_type
    assert controller.capability(provider_type) == capability
    provider = controller.llm(name) if capability == "llm" else controller.tts(name)
    assert provider.provider_id == name
    monkeypatch.setattr(provider, "health", lambda: ProviderHealth(True, "adapter-ready"))
    health = controller.health(name)
    assert health.healthy is True
    assert health.message == "adapter-ready"

    persisted = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert all(secret not in persisted for secret in secrets.values())


def test_provider_controller_diagnostics_do_not_emit_credential_value(tmp_path) -> None:
    secret = "do-not-leak-this-provider-secret"
    controller = _controller(tmp_path, environ={"PRIVATE_PROVIDER_KEY": secret})

    controller.save_provider(
        "remote",
        "openai",
        default_model="gpt-test",
        credential_env="PRIVATE_PROVIDER_KEY",
    )

    assert secret not in repr(controller.config())
    assert secret not in (tmp_path / "config.json").read_text(encoding="utf-8")


def test_invalid_provider_configuration_is_not_persisted(tmp_path) -> None:
    controller = _controller(tmp_path)

    with pytest.raises(ValueError, match="base_url"):
        controller.save_provider("planner", "fake", base_url="not-a-url")

    assert "planner" not in controller.config().providers


def test_save_rejects_generic_legacy_capability(tmp_path) -> None:
    controller = _controller(tmp_path)

    with pytest.raises(ValueError, match="unsupported provider adapter"):
        controller.save_provider("legacy", "llm")
