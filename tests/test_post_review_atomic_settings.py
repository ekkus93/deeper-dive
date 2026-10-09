"""Atomic multi-default saves must not partly publish one logical setting change."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.user_config import UserConfig, UserConfigStore


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
    store.save(UserConfig(defaults={"keep": "unchanged"}))
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
