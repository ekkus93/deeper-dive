from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.settings_screen import SettingsController, SettingsScreen
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _provider_controller(tmp_path: Path) -> ProviderController:
    store = UserConfigStore(tmp_path / "config.json")
    store.save(
        UserConfig(
            providers={
                "planner": ProviderConfig(
                    provider_type="fake",
                    default_model="model-a",
                    network_scope="local",
                ),
                "fake-tts": ProviderConfig(
                    provider_type="fake-tts",
                    network_scope="local",
                    voices=("voice-a",),
                ),
            }
        )
    )
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


def test_settings_controller_reports_runtime_readiness(tmp_path: Path) -> None:
    controller = SettingsController(_provider_controller(tmp_path))
    controller.save_runtime_defaults("custom-ffmpeg", "", "normal")

    with (
        patch("deeper_dive.settings_screen.shutil.which", return_value="/opt/bin/custom-ffmpeg"),
        patch("deeper_dive.settings_screen.importlib.util.find_spec", return_value=object()),
    ):
        summary = controller.readiness_summary()

    assert "FFmpeg: /opt/bin/custom-ffmpeg" in summary
    assert "KittenTTS: runtime installed" in summary
    assert any("KittenML/kitten-tts-micro-0.8" in row for row in summary)


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
        readiness = str(app.screen.query_one("#readiness-status", Static).render())
        assert "Runtime readiness" in readiness
        assert "FFmpeg:" in readiness
        assert "KittenTTS:" in readiness


def test_settings_rejects_unknown_or_wrong_capability_provider_references(tmp_path: Path) -> None:
    controller = SettingsController(_provider_controller(tmp_path))
    store = controller.provider_controller.config_store
    original = store.path.read_bytes()

    with pytest.raises(ValueError, match="unknown provider"):
        controller.save_model_default("episode_planning", "missing:model-a")
    assert store.path.read_bytes() == original

    with pytest.raises(ValueError, match="language-model provider"):
        controller.save_model_default("episode_planning", "fake-tts:model-a")
    assert store.path.read_bytes() == original

    with pytest.raises(ValueError, match="unknown provider"):
        controller.save_tts_defaults("missing", "voice-a")
    assert store.path.read_bytes() == original

    with pytest.raises(ValueError, match="speech provider"):
        controller.save_tts_defaults("planner", "voice-a")
    assert store.path.read_bytes() == original


def test_provider_removal_preserves_stale_assignment_for_preflight_repair(
    tmp_path: Path,
) -> None:
    controller = _provider_controller(tmp_path)
    settings = SettingsController(controller)
    settings.save_model_default("episode_planning", "planner:model-a")

    controller.remove_provider("planner")

    config = controller.config()
    assert "planner" not in config.providers
    assert config.defaults["episode_planning"] == "planner:model-a"
    with pytest.raises(KeyError, match="unknown LLM provider"):
        controller.llm_registry.get("planner")


def test_local_provider_ids_reject_unknown_provider_before_save(tmp_path: Path) -> None:
    controller = SettingsController(_provider_controller(tmp_path))
    original = controller.provider_controller.config_store.path.read_bytes()

    with pytest.raises(ValueError, match="local_provider_ids"):
        controller.set_default("local_provider_ids", "planner,missing")

    assert controller.provider_controller.config_store.path.read_bytes() == original


def test_settings_screen_handles_config_io_failure_without_discarding_input(
    tmp_path: Path,
) -> None:
    asyncio.run(_settings_screen_handles_config_io_failure_without_discarding_input(tmp_path))


async def _settings_screen_handles_config_io_failure_without_discarding_input(
    tmp_path: Path,
) -> None:
    """Failed durable writes preserve the edited form and sanitize error context."""
    controller = _provider_controller(tmp_path)
    store = controller.config_store
    original = store.path.read_bytes()
    app = DeeperDiveApp(
        DeeperDiveService(WorkspaceManager(tmp_path / "data")),
        provider_controller=controller,
    )
    canary = "settings-io-failure-canary"
    endpoint = f"https://example.test/v1?api%5Fkey={canary}"

    def fail_write(self: SettingsController, key: str, value: str) -> None:
        _ = (self, key, value)
        try:
            raise ValueError(f"remote provider failed: {endpoint}")
        except ValueError as cause:
            raise OSError("unable to persist settings") from cause

    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("settings")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SettingsScreen)
        screen.query_one("#settings-key", Input).value = "local_only"
        screen.query_one("#settings-value", Input).value = "true"
        with patch.object(SettingsController, "set_default", fail_write):
            screen.action_save_default()
        await pilot.pause()
        assert app.screen is screen
        assert screen.query_one("#settings-value", Input).value == "true"
        status = str(screen.query_one("#screen-status", Static).render())
        assert "unable to persist settings" in status
        assert "caused by:" in status
        assert canary not in status
        assert "[REDACTED]" in status
        assert store.path.read_bytes() == original


@pytest.mark.parametrize("key", ("tts_voice", "tts_voice_host_1", "tts_voice_host_2"))
def test_settings_rejects_voice_not_declared_by_selected_provider_without_writing(
    tmp_path: Path, key: str
) -> None:
    controller = SettingsController(_provider_controller(tmp_path))
    controller.save_tts_defaults("fake-tts", "voice-a")
    config_store = controller.provider_controller.config_store
    original_bytes = config_store.path.read_bytes()
    rejected_canary = "unknown-voice-canary"

    with pytest.raises(ValueError, match=f"{key} references a voice") as error:
        controller.set_defaults({key: rejected_canary})

    assert rejected_canary not in str(error.value)
    assert config_store.path.read_bytes() == original_bytes
    assert config_store.load().defaults["tts_voice"] == "voice-a"


def test_provider_default_updates_reject_unknown_declared_voice_atomically(
    tmp_path: Path,
) -> None:
    controller = _provider_controller(tmp_path)
    path = controller.config_store.path
    original_bytes = path.read_bytes()

    with pytest.raises(ValueError, match="tts_voice references a voice") as error:
        controller.save_provider(
            "fake-tts",
            "fake-tts",
            voices=("voice-a",),
            default_updates={
                "tts_provider": "fake-tts",
                "tts_voice": "unknown-voice-canary",
            },
        )

    assert "unknown-voice-canary" not in str(error.value)
    assert path.read_bytes() == original_bytes
    assert controller.config().defaults.get("tts_voice") is None


def test_settings_allow_voice_for_provider_without_static_voice_catalog(
    tmp_path: Path,
) -> None:
    controller = _provider_controller(tmp_path)
    controller.save_provider("dynamic-speech", "openai-tts")
    settings = SettingsController(controller)
    settings.save_tts_defaults("dynamic-speech", "discovered-voice-id")

    config = controller.config_store.load()
    assert config.defaults["tts_provider"] == "dynamic-speech"
    assert config.defaults["tts_voice"] == "discovered-voice-id"
