"""Settings validation must not echo rejected user input before shared config checks."""

from __future__ import annotations

import pytest

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.user_config import MAX_QUICK_DURATION_MINUTES, UserConfigStore


@pytest.mark.parametrize(
    "rejected",
    [
        "not-an-integer-canary",
        "-1",
        str(MAX_QUICK_DURATION_MINUTES + 1),
    ],
)
def test_quick_duration_invalid_input_is_rejected_without_echo_or_partial_write(
    tmp_path, rejected: str
) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    settings = SettingsController(ProviderController(store, LLMProviderRegistry(), {}))
    with pytest.raises(ValueError) as caught:
        settings.save_quick_deep_dive_defaults(rejected, "curious_explainer,skeptic", "useful")
    assert rejected not in str(caught.value)
    assert not store.path.exists()
