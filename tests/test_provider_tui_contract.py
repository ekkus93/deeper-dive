from __future__ import annotations

from deeper_dive.llm import LLMProviderRegistry, ProviderHealth
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import UserConfigStore


def _controller(tmp_path) -> ProviderController:
    return ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(
            environ={
                "OPENAI_TEST_KEY": "secret-openai",
                "ELEVEN_TEST_KEY": "secret-eleven",
            }
        ),
    )


def test_configuration_fields_explain_adapter_specific_ui_surface(tmp_path) -> None:
    controller = _controller(tmp_path)

    assert "credential_env" in controller.configuration_fields("openai")
    assert "timeout_seconds" in controller.configuration_fields("ollama")
    assert "network_scope" in controller.configuration_fields("kitten")
    assert "response_format" in controller.configuration_fields("openai-compatible-tts")
    assert "voices" in controller.configuration_fields("openai-compatible-tts")
    assert "voices" not in controller.configuration_fields("openai-tts")
    assert "credential_env" not in controller.configuration_fields("fake")


def test_health_routes_through_llm_runtime_adapter(tmp_path, monkeypatch) -> None:
    controller = _controller(tmp_path)
    controller.save_provider("planner", "fake", default_model="fake-v1")
    provider = controller.llm("planner")
    monkeypatch.setattr(provider, "health", lambda: ProviderHealth(True, "llm-ready"))

    health = controller.health("planner")

    assert health.healthy is True
    assert health.message == "llm-ready"


def test_health_routes_through_tts_runtime_adapter(tmp_path, monkeypatch) -> None:
    controller = _controller(tmp_path)
    controller.save_provider("speech", "fake-tts")
    provider = controller.tts("speech")
    monkeypatch.setattr(provider, "health", lambda: ProviderHealth(True, "tts-ready"))

    health = controller.health("speech")

    assert health.healthy is True
    assert health.message == "tts-ready"
