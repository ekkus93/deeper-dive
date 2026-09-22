from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Static

from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController, SettingsScreen
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.user_config import UserConfigStore
from deeper_dive.tui import DeeperDiveApp


def _provider_controller(tmp_path: Path) -> ProviderController:
    store = UserConfigStore(tmp_path / "config.json")
    return ProviderController(store, LLMProviderRegistry(), {"fake-tts": FakeTTSProvider()})


def test_settings_controller_persists_structured_defaults(tmp_path: Path) -> None:
    controller = SettingsController(_provider_controller(tmp_path))

    controller.save_model_default("episode_planning", "planner:model-a")
    controller.save_tts_defaults("fake-tts", "voice-a")
    controller.save_research_defaults("useful", "local-only")
    controller.save_quick_deep_dive_defaults("25", "curious_explainer,skeptic", "useful")
    controller.save_runtime_defaults("/usr/bin/ffmpeg", "/models/kitten", "verbose")

    defaults = controller.provider_controller.config().defaults
    assert defaults["episode_planning"] == "planner:model-a"
    assert defaults["tts_provider"] == "fake-tts"
    assert defaults["tts_voice"] == "voice-a"
    assert defaults["research_policy"] == "useful"
    assert defaults["network_policy"] == "local-only"
    assert defaults["quick_deep_dive_duration_minutes"] == "25"
    assert defaults["quick_deep_dive_host_presets"] == "curious_explainer,skeptic"
    assert defaults["quick_deep_dive_research_policy"] == "useful"
    assert defaults["ffmpeg_executable"] == "/usr/bin/ffmpeg"
    assert defaults["kitten_model_dir"] == "/models/kitten"
    assert defaults["diagnostic_logging"] == "verbose"


def test_settings_controller_removes_blank_default(tmp_path: Path) -> None:
    controller = SettingsController(_provider_controller(tmp_path))

    controller.set_default("local_only", "true")
    controller.set_default("local_only", "")

    assert "local_only" not in controller.provider_controller.config().defaults


def test_settings_controller_validates_model_default(tmp_path: Path) -> None:
    controller = SettingsController(_provider_controller(tmp_path))

    try:
        controller.save_model_default("episode_planning", "missing-separator")
    except ValueError as exc:
        assert "provider:model" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected invalid model default to fail")


def test_settings_screen_persists_default_from_tui_action(tmp_path: Path) -> None:
    asyncio.run(_settings_screen_persists_default_from_tui_action(tmp_path))


async def _settings_screen_persists_default_from_tui_action(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = DeeperDiveApp(service, provider_controller=_provider_controller(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("settings")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        app.screen.query_one("#settings-key", Input).value = "local_only"
        app.screen.query_one("#settings-value", Input).value = "true"
        app.screen.action_save_default()
        await pilot.pause()
        assert "Saved default" in str(app.screen.query_one("#screen-status", Static).render())
        assert app.provider_controller.config().defaults["local_only"] == "true"
