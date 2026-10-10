"""Atomic multi-default saves must not partly publish one logical setting change."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class CountingStore(UserConfigStore):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.writes = 0
        self.fail = False

    def save(self, config: UserConfig) -> None:
        self.writes += 1
        if self.fail:
            raise OSError("simulated disk write failure")
        super().save(config)


def _settings(tmp_path: Path) -> tuple[SettingsController, CountingStore]:
    store = CountingStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    network_scope="local",
                    voices=("voice-a",),
                )
            },
            defaults={"keep": "unchanged"},
        )
    )
    store.writes = 0
    controller = SettingsController(ProviderController(store, LLMProviderRegistry(), {}))
    return controller, store


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("save_tts_defaults", ("speech", "voice-a")),
        ("save_research_defaults", ("off", "local-only")),
        ("save_quick_deep_dive_defaults", ("25", "skeptic,curious_explainer", "off")),
        ("save_runtime_defaults", ("ffmpeg", "/models", "normal")),
    ],
)
def test_each_logical_multi_setting_save_is_one_write(
    tmp_path: Path, method: str, args: tuple[str, ...]
) -> None:
    controller, store = _settings(tmp_path)
    getattr(controller, method)(*args)
    assert store.writes == 1
    assert controller.provider_controller.config().defaults["keep"] == "unchanged"


def test_validation_failure_does_not_write_any_setting(tmp_path: Path) -> None:
    controller, store = _settings(tmp_path)
    original = store.path.read_bytes()
    with pytest.raises(ValueError):
        controller.set_defaults({"valid": "new", "": "bad"})
    assert store.writes == 0
    assert store.path.read_bytes() == original


def test_failed_atomic_batch_does_not_write_partial_config(tmp_path: Path) -> None:
    controller, store = _settings(tmp_path)
    original = store.path.read_bytes()
    store.fail = True
    with pytest.raises(OSError):
        controller.save_tts_defaults("speech", "voice-a")
    assert store.writes == 1
    assert store.path.read_bytes() == original


def test_speech_provider_and_defaults_use_one_write(tmp_path: Path) -> None:
    store = CountingStore(tmp_path / "config.json")
    controller = ProviderController(store, LLMProviderRegistry(), {})
    controller.save_provider(
        "speech",
        "fake-tts",
        voices=("voice-a",),
        default_updates={
            "speech_setup": "configured",
            "tts_provider": "speech",
            "tts_voice": "",
        },
    )
    assert store.writes == 1
    config = store.load()
    assert config.providers["speech"].voices == ("voice-a",)
    assert config.defaults["speech_setup"] == "configured"
    assert config.defaults["tts_provider"] == "speech"
    assert "tts_voice" not in config.defaults


def test_speech_provider_save_failure_preserves_previous_bytes(tmp_path: Path) -> None:
    store = CountingStore(tmp_path / "config.json")
    store.save(UserConfig(defaults={"speech_setup": "deferred"}))
    original = store.path.read_bytes()
    store.writes = 0
    store.fail = True
    controller = ProviderController(store, LLMProviderRegistry(), {})
    with pytest.raises(OSError, match="simulated disk write failure"):
        controller.save_provider(
            "speech",
            "fake-tts",
            default_updates={"speech_setup": "configured", "tts_provider": "speech"},
        )
    assert store.writes == 1
    assert store.path.read_bytes() == original
    assert "speech" not in store.load().providers


def test_invalid_speech_default_batch_cannot_persist_provider(tmp_path: Path) -> None:
    store = CountingStore(tmp_path / "config.json")
    controller = ProviderController(store, LLMProviderRegistry(), {})
    with pytest.raises(ValueError, match="settings key is required"):
        controller.save_provider(
            "speech",
            "fake-tts",
            default_updates={"speech_setup": "configured", " ": "bad"},
        )
    assert store.writes == 0
    assert not store.path.exists()
