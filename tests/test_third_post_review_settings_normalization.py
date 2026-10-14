"""TPR-19.3: every default writer normalizes before checking references."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _controller(tmp_path: Path) -> ProviderController:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={
                "planner": ProviderConfig(
                    provider_type="fake", default_model="model-a", network_scope="local"
                ),
            }
        )
    )
    return ProviderController(store, LLMProviderRegistry(), {"fake-tts": FakeTTSProvider()})


@pytest.mark.parametrize("raw", ["planner:model-a", "planner :model-a", " planner : model-a "])
def test_settings_and_provider_save_store_identical_normalized_value(
    tmp_path: Path, raw: str
) -> None:
    (tmp_path / "settings").mkdir()
    (tmp_path / "provider").mkdir()
    via_settings = _controller(tmp_path / "settings")
    via_provider = _controller(tmp_path / "provider")

    SettingsController(via_settings).save_model_default("research_planning", raw)
    via_provider.save_provider(
        "planner",
        "fake",
        default_model="model-a",
        network_scope="local",
        default_updates={"research_planning": raw},
    )

    expected = "planner:model-a"
    assert via_settings.config().defaults["research_planning"] == expected
    assert via_provider.config().defaults["research_planning"] == expected


def test_settings_reports_unknown_provider_only_when_it_is_actually_unknown(
    tmp_path: Path,
) -> None:
    (tmp_path / "a").mkdir()
    controller = _controller(tmp_path / "a")
    with pytest.raises(ValueError, match="unknown provider"):
        SettingsController(controller).save_model_default("research_planning", "missing:model-a")
