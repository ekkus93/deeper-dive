"""Cross-surface regression for durable configuration key validation."""

from __future__ import annotations

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.user_config import UserConfig, UserConfigStore


@pytest.mark.parametrize("key", ["research_policy", "network_policy"])
def test_known_default_keys_accept_valid_values(key: str) -> None:
    value = "useful" if key == "research_policy" else "local-only"
    assert UserConfig(defaults={key: value}).defaults[key] == value


@pytest.mark.parametrize("codepoint", [0, 9, 10, 13, 27, 127])
@pytest.mark.parametrize("surface", ["settings", "provider"])
def test_invalid_default_keys_are_rejected_before_any_write(
    tmp_path, codepoint: int, surface: str
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"research_policy": "useful"}))
    original = store.path.read_bytes()
    provider = ProviderController(store, LLMProviderRegistry(), {})
    invalid_key = "extension" + chr(codepoint) + "name"
    with pytest.raises(ValueError, match="single-line"):
        if surface == "settings":
            SettingsController(provider).set_default(invalid_key, "value")
        else:
            provider.save_provider("local", "fake", default_updates={invalid_key: "value"})
    assert store.path.read_bytes() == original
    assert store.load().defaults == {"research_policy": "useful"}


def test_legacy_extension_value_survives_store_restart(tmp_path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    text = "line one" + chr(10) + "line two"
    store.save(UserConfig(defaults={"extension_custom": text}))
    assert UserConfigStore(store.path).load().defaults["extension_custom"] == text
