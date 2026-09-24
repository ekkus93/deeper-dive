from __future__ import annotations

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import UserConfigStore


def _controller(tmp_path) -> ProviderController:
    return ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={}),
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
    assert tuple(voice.voice_id for voice in controller.tts("speech").voices()) == (
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


def test_invalid_provider_configuration_is_not_persisted(tmp_path) -> None:
    controller = _controller(tmp_path)

    with pytest.raises(ValueError, match="base_url"):
        controller.save_provider("planner", "fake", base_url="not-a-url")

    assert "planner" not in controller.config().providers


def test_save_rejects_generic_legacy_capability(tmp_path) -> None:
    controller = _controller(tmp_path)

    with pytest.raises(ValueError, match="unsupported provider adapter"):
        controller.save_provider("legacy", "llm")
