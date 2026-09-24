from __future__ import annotations

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import UserConfigStore


def _controller(tmp_path, environ=None) -> ProviderController:
    return ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={} if environ is None else environ),
    )


def test_openai_style_llm_save_reload_and_health(tmp_path) -> None:
    controller = _controller(tmp_path, {"TEST_OPENAI_KEY": "super-secret-value"})
    controller.save_provider(
        "openai-main",
        "openai",
        default_model="gpt-test",
        credential_env="TEST_OPENAI_KEY",
        timeout_seconds=9.0,
        network_scope="remote",
    )

    saved = controller.config().providers["openai-main"]
    assert saved.credential_env == "TEST_OPENAI_KEY"
    assert saved.timeout_seconds == 9.0
    assert saved.network_scope == "remote"
    assert controller.llm("openai-main").provider_id == "openai-main"
    assert controller.llm("openai-main").models()[0].model == "gpt-test"
    assert "super-secret-value" not in repr(saved)


def test_ollama_save_reload_and_health(tmp_path) -> None:
    controller = _controller(tmp_path)
    controller.save_provider(
        "ollama-local",
        "ollama",
        base_url="http://127.0.0.1:11434",
        default_model="qwen-test",
        timeout_seconds=4.0,
        network_scope="local",
    )

    saved = controller.config().providers["ollama-local"]
    assert saved.base_url == "http://127.0.0.1:11434"
    assert saved.network_scope == "local"
    assert controller.llm("ollama-local").provider_id == "ollama-local"
    assert controller.llm("ollama-local").models()[0].model == "qwen-test"


def test_openai_compatible_local_llm_save_reload_and_health(tmp_path) -> None:
    controller = _controller(tmp_path)
    controller.save_provider(
        "local-openai",
        "llama-server",
        base_url="http://127.0.0.1:8080",
        default_model="local-model",
        timeout_seconds=5.0,
        network_scope="local",
    )

    saved = controller.config().providers["local-openai"]
    assert saved.base_url == "http://127.0.0.1:8080"
    assert saved.network_scope == "local"
    assert controller.llm("local-openai").provider_id == "local-openai"
    assert controller.llm("local-openai").models()[0].model == "local-model"


def test_kittentts_save_reload_and_health(tmp_path) -> None:
    controller = _controller(tmp_path)
    controller.save_provider("kitten-local", "kitten", network_scope="local")

    saved = controller.config().providers["kitten-local"]
    assert saved.network_scope == "local"
    assert controller.tts("kitten-local").provider_id == "kitten-local"


def test_openai_tts_save_reload_and_health(tmp_path) -> None:
    controller = _controller(tmp_path, {"TEST_OPENAI_TTS_KEY": "tts-secret-value"})
    controller.save_provider(
        "openai-speech",
        "openai-tts",
        default_model="tts-test",
        credential_env="TEST_OPENAI_TTS_KEY",
        timeout_seconds=8.0,
        network_scope="remote",
    )

    saved = controller.config().providers["openai-speech"]
    assert saved.credential_env == "TEST_OPENAI_TTS_KEY"
    assert saved.network_scope == "remote"
    assert controller.tts("openai-speech").provider_id == "openai-speech"
    assert "tts-secret-value" not in repr(saved)


def test_openai_compatible_tts_save_reload_voice_catalog_and_health(tmp_path) -> None:
    controller = _controller(tmp_path)
    controller.save_provider(
        "local-speech",
        "openai-compatible-tts",
        base_url="http://127.0.0.1:9000/v1",
        default_model="tts-local",
        response_format="mp3",
        voices=("alice", "bob"),
        timeout_seconds=6.0,
        network_scope="local",
    )

    saved = controller.config().providers["local-speech"]
    assert saved.response_format == "mp3"
    assert saved.voices == ("alice", "bob")
    assert tuple(voice.id for voice in controller.tts("local-speech").voices()) == ("alice", "bob")


def test_elevenlabs_style_tts_save_reload_and_health(tmp_path) -> None:
    controller = _controller(tmp_path, {"TEST_ELEVEN_KEY": "eleven-secret-value"})
    controller.save_provider(
        "eleven-speech",
        "elevenlabs",
        default_model="eleven-test",
        credential_env="TEST_ELEVEN_KEY",
        timeout_seconds=7.0,
        network_scope="remote",
    )

    saved = controller.config().providers["eleven-speech"]
    assert saved.credential_env == "TEST_ELEVEN_KEY"
    assert saved.network_scope == "remote"
    assert controller.tts("eleven-speech").provider_id == "eleven-speech"
    assert "eleven-secret-value" not in repr(saved)


@pytest.mark.parametrize(
    ("provider_type", "kwargs"),
    [
        ("fake", {"default_model": "fake-v1"}),
        ("fake-tts", {}),
    ],
)
def test_provider_controller_never_persists_environment_secret_values(
    tmp_path, provider_type, kwargs
) -> None:
    config_path = tmp_path / "config.json"
    controller = ProviderController(
        UserConfigStore(config_path),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={"SHOULD_NOT_LEAK": "raw-secret"}),
    )
    controller.save_provider(
        "provider",
        provider_type,
        credential_env="SHOULD_NOT_LEAK",
        **kwargs,
    )

    payload = config_path.read_text(encoding="utf-8")
    assert "SHOULD_NOT_LEAK" in payload
    assert "raw-secret" not in payload
