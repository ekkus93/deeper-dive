from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry, ProviderHealth
from deeper_dive.provider_tui import ProviderController
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import TTSVoice
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfigStore


class FakeTTSProvider:
    provider_id = "speech"

    def health(self) -> ProviderHealth:
        return ProviderHealth(True, "ready")

    def voices(self) -> tuple[TTSVoice, ...]:
        return (TTSVoice("alice", "Alice"), TTSVoice("bob", "Bob"))


def test_providers_tui_configure_health_and_discovery(tmp_path: Path) -> None:
    asyncio.run(_providers_workflow(tmp_path))


async def _providers_workflow(tmp_path: Path) -> None:
    registry = LLMProviderRegistry()
    registry.register(FakeLLMProvider(provider_id="fake"))
    controller = ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        registry,
        {"speech": FakeTTSProvider()},
    )
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = DeeperDiveApp(service, provider_controller=controller)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        assert isinstance(app.screen, ProvidersScreen)
        screen = app.screen

        screen.query_one("#provider-name", Input).value = "fake"
        screen.query_one("#provider-type", Input).value = "llm"
        screen.action_save()
        screen.action_health()
        assert "healthy" in _text(screen, "#screen-status")
        screen.action_models()
        assert "fake-v1" in _text(screen, "#provider-details")
        assert "streaming=True" in _text(screen, "#provider-details")

        screen.query_one("#provider-name", Input).value = "speech"
        screen.query_one("#provider-type", Input).value = "tts"
        screen.action_save()
        assert "fake" in _text(screen, "#llm-provider-list")
        assert "speech" in _text(screen, "#tts-provider-list")
        screen.action_health()
        assert "healthy" in _text(screen, "#screen-status")
        screen.action_voices()
        assert "alice" in _text(screen, "#provider-details")
        assert "bob" in _text(screen, "#provider-details")

        screen.action_remove()
        assert "speech" not in controller.config().providers


def test_provider_errors_are_actionable(tmp_path: Path) -> None:
    asyncio.run(_provider_error_workflow(tmp_path))


async def _provider_error_workflow(tmp_path: Path) -> None:
    controller = ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
    )
    app = DeeperDiveApp(
        DeeperDiveService(WorkspaceManager(tmp_path / "data")),
        provider_controller=controller,
    )
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ProvidersScreen)
        screen.query_one("#provider-name", Input).value = "missing"
        screen.query_one("#provider-type", Input).value = "llm"
        screen.action_save()
        screen.action_health()
        assert "unavailable" in _text(screen, "#screen-status")


def _text(screen: ProvidersScreen, selector: str) -> str:
    return str(screen.query_one(selector, Static).render())
