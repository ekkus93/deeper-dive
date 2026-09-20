from __future__ import annotations

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import UserConfigStore


def test_save_concrete_adapter_reloads_runtime_registry(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    controller = ProviderController(
        store,
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={}),
    )

    controller.save_provider("planner", "fake", default_model="fake-v2")

    assert controller.config().providers["planner"].provider_type == "fake"
    assert controller.capability("fake") == "llm"
    assert controller.llm("planner").models()[0].model == "fake-v2"


def test_save_tts_adapter_reloads_runtime_provider(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    controller = ProviderController(
        store,
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={}),
    )

    controller.save_provider("speech", "fake_tts")

    assert controller.config().providers["speech"].provider_type == "fake-tts"
    assert controller.capability("fake-tts") == "tts"
    assert controller.tts("speech").provider_id == "speech"


def test_save_rejects_generic_legacy_capability(tmp_path) -> None:
    controller = ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={}),
    )

    with pytest.raises(ValueError, match="unsupported provider adapter"):
        controller.save_provider("legacy", "llm")
