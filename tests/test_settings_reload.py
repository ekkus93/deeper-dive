from __future__ import annotations

from pathlib import Path

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController
from deeper_dive.user_config import UserConfigStore


def _provider_controller(path: Path) -> ProviderController:
    return ProviderController(
        UserConfigStore(path),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={}),
    )


def test_settings_reload_from_durable_store_after_controller_reconstruction(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    first = SettingsController(_provider_controller(path))
    first.save_model_default("episode_planning", "fake:fake-v1")
    first.save_tts_defaults("fake-tts", "voice-a")
    first.save_research_defaults("useful", "local-only")
    first.save_quick_deep_dive_defaults("25", "curious_explainer,skeptic", "useful")
    first.save_runtime_defaults("ffmpeg", "/models/kitten", "verbose")

    reconstructed = _provider_controller(path)
    defaults = reconstructed.config().defaults

    assert defaults["episode_planning"] == "fake:fake-v1"
    assert defaults["tts_provider"] == "fake-tts"
    assert defaults["tts_voice"] == "voice-a"
    assert defaults["research_policy"] == "useful"
    assert defaults["network_policy"] == "local-only"
    assert defaults["quick_deep_dive_duration_minutes"] == "25"
    assert defaults["quick_deep_dive_host_presets"] == "curious_explainer,skeptic"
    assert defaults["quick_deep_dive_research_policy"] == "useful"
    assert defaults["ffmpeg_executable"] == "ffmpeg"
    assert defaults["kitten_model_dir"] == "/models/kitten"
    assert defaults["diagnostic_logging"] == "verbose"
