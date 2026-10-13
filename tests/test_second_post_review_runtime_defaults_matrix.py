"""SPR-04: production Settings/defaults normalisation and atomic rollback matrix."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _settings(tmp_path: Path) -> tuple[UserConfigStore, SettingsController]:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={
                "local": ProviderConfig(provider_type="fake"),
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    voices=("voice-a", "voice-b"),
                ),
            },
            defaults={
                "tts_provider": "speech",
                "tts_voice": "voice-a",
                "network_policy": "local-only",
                "diagnostic_logging": "normal",
                "research_policy": "off",
                "custom_legacy_extension": "  retain as-is  ",
            },
        )
    )
    return store, SettingsController(ProviderController(store, LLMProviderRegistry(), {}))


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("research_policy", " CONSERVATIVE ", "conservative"),
        ("quick_deep_dive_research_policy", " AGGRESSIVE ", "aggressive"),
        ("quick_deep_dive_duration_minutes", " 30 ", "30"),
        (
            "quick_deep_dive_host_presets",
            " curious_explainer, skeptic ",
            "curious_explainer,skeptic",
        ),
        ("local_only", " YES ", "yes"),
        ("network_policy", " CONFIGURED_PROVIDERS ", "configured-providers"),
        ("diagnostic_logging", " VERBOSE ", "verbose"),
        ("speech_setup", " DEFERRED ", "deferred"),
        ("ffmpeg_executable", " /usr/bin/ffmpeg ", "/usr/bin/ffmpeg"),
        ("kitten_model_dir", " /tmp/kitten-fixture ", "/tmp/kitten-fixture"),
        ("local_provider_ids", " local, speech ", "local,speech"),
        ("tts_provider", " speech ", "speech"),
        ("tts_voice", " voice-a ", "voice-a"),
        ("tts_voice_host_1", " voice-a ", "voice-a"),
        ("tts_voice_host_2", " voice-b ", "voice-b"),
        ("host_generation", " local:fake-v1 ", "local:fake-v1"),
    ],
)
def test_each_runtime_default_normalizes_and_survives_reload(
    tmp_path: Path, key: str, raw: str, expected: str
) -> None:
    store, settings = _settings(tmp_path)
    settings.set_default(key, raw)
    loaded = UserConfigStore(store.path).load()
    assert loaded.defaults[key] == expected
    assert loaded.defaults["custom_legacy_extension"] == "  retain as-is  "
    assert set(loaded.providers) == {"local", "speech"}


@pytest.mark.parametrize(
    ("invalid_key", "invalid_value"),
    [
        ("research_policy", "most"),
        ("quick_deep_dive_research_policy", "unknown"),
        ("quick_deep_dive_duration_minutes", "0"),
        ("quick_deep_dive_duration_minutes", "9223372036854775807"),
        ("quick_deep_dive_host_presets", "skeptic"),
        ("quick_deep_dive_host_presets", "skeptic,unknown"),
        ("local_only", "truthy"),
        ("network_policy", "no-network"),
        ("diagnostic_logging", "all"),
        ("speech_setup", "done"),
        ("ffmpeg_executable", "bin\nsh"),
        ("kitten_model_dir", "/tmp/\x00broken"),
        ("local_provider_ids", "local,missing"),
        ("tts_provider", "missing"),
        ("tts_voice", "undeclared"),
        ("tts_voice_host_2", "not-a-voice"),
        ("host_generation", "bare-model"),
        ("host_generation", "missing:fake-v1"),
    ],
)
def test_invalid_composite_settings_preserve_original_bytes_and_defaults(
    tmp_path: Path, invalid_key: str, invalid_value: str
) -> None:
    store, settings = _settings(tmp_path)
    before = store.path.read_bytes()
    previous = UserConfigStore(store.path).load()
    valid_update = (
        {"diagnostic_logging": "verbose"}
        if invalid_key == "research_policy"
        else {"research_policy": "useful"}
    )
    with pytest.raises(ValueError) as caught:
        settings.set_defaults({**valid_update, invalid_key: invalid_value})
    assert "canary" not in str(caught.value)
    assert store.path.read_bytes() == before
    assert UserConfigStore(store.path).load().defaults == previous.defaults


def test_settings_blank_removes_only_selected_default(tmp_path: Path) -> None:
    store, settings = _settings(tmp_path)
    settings.set_defaults({"network_policy": "", "diagnostic_logging": "  "})
    loaded = UserConfigStore(store.path).load()
    assert "network_policy" not in loaded.defaults
    assert "diagnostic_logging" not in loaded.defaults
    assert loaded.defaults["research_policy"] == "off"
    assert loaded.defaults["custom_legacy_extension"] == "  retain as-is  "


def test_valid_composite_settings_batch_uses_one_durable_save(tmp_path: Path) -> None:
    store, settings = _settings(tmp_path)
    with patch.object(store, "save", wraps=store.save) as writer:
        settings.set_defaults(
            {
                "local_only": " no ",
                "network_policy": " ALLOW_REMOTE ",
                "diagnostic_logging": " verbose ",
            }
        )
    assert writer.call_count == 1
    loaded = UserConfigStore(store.path).load()
    assert loaded.defaults["local_only"] == "no"
    assert loaded.defaults["network_policy"] == "allow-remote"
    assert loaded.defaults["diagnostic_logging"] == "verbose"
