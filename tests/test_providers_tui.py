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
        screen.query_one("#provider-type", Input).value = "fake"
        screen.action_save()
        screen.action_health()
        assert "healthy" in _text(screen, "#screen-status")
        screen.action_models()
        assert "fake-v1" in _text(screen, "#provider-details")
        assert "streaming=True" in _text(screen, "#provider-details")

        screen.query_one("#provider-name", Input).value = "speech"
        screen.query_one("#provider-type", Input).value = "fake-tts"
        screen.action_save()
        assert "fake" in _text(screen, "#llm-provider-list")
        assert "speech" in _text(screen, "#tts-provider-list")
        screen.action_health()
        assert "healthy" in _text(screen, "#screen-status")
        screen.action_voices()
        assert "alice" in _text(screen, "#provider-details")
        assert "bob" in _text(screen, "#provider-details")

        screen.action_remove()
        assert "speech" in controller.config().providers
        screen.action_confirm_remove()
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
        screen.query_one("#provider-type", Input).value = "fake"
        screen.action_save()
        screen.action_health()
        assert "Provider request failed." in _text(screen, "#screen-status")


def _text(screen: ProvidersScreen, selector: str) -> str:
    return str(screen.query_one(selector, Static).render())


def test_provider_originated_health_discovery_and_errors_are_redacted(tmp_path, monkeypatch):
    asyncio.run(_secret_provider_workflow(tmp_path, monkeypatch))


async def _secret_provider_workflow(tmp_path, monkeypatch):
    from deeper_dive.llm import LLMCapabilities, LLMModel
    from deeper_dive.provider_factory import ProviderFactory

    secrets = [f"synthetic-secret-{i}" for i in range(7)]
    text = "; ".join(
        [
            f"Authorization: {secrets[0]}",
            f"Bearer {secrets[1]}",
            f"access_token={secrets[2]}",
            f"refresh_token={secrets[3]}",
            f"client_secret={secrets[4]}",
            f"cookie={secrets[5]}",
            f"https://user:{secrets[6]}@example.test",
        ]
    )
    controller = ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={}),
    )
    controller.save_provider("dialogue", "fake")
    controller.save_provider("speech", "fake-tts")
    app = DeeperDiveApp(
        DeeperDiveService(WorkspaceManager(tmp_path / "data")), provider_controller=controller
    )
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = app.screen
        for name, kind in [("dialogue", "llm"), ("speech", "tts")]:
            screen.query_one("#provider-name", Input).value = name
            provider = controller.llm(name) if kind == "llm" else controller.tts(name)
            monkeypatch.setattr(provider, "health", lambda: ProviderHealth(True, "ready " + text))
            screen.action_health()
            status = _text(screen, "#screen-status")
            assert "ready" in status and "[REDACTED]" in status
            assert all(secret not in status for secret in secrets)
            if kind == "llm":
                monkeypatch.setattr(
                    provider,
                    "models",
                    lambda: (LLMModel("dialogue", "plain-model " + text, LLMCapabilities()),),
                )
                screen.action_models()
                plain = "plain-model"
            else:
                monkeypatch.setattr(
                    provider,
                    "voices",
                    lambda: (TTSVoice("voice-id " + text, "Plain Voice " + text),),
                )
                screen.action_voices()
                plain = "Plain Voice"
            details = _text(screen, "#provider-details")
            assert plain in details and "[REDACTED]" in details
            assert all(secret not in details for secret in secrets)

            def fail():
                raise ValueError(text)

            monkeypatch.setattr(provider, "health", fail)
            screen.action_health()
            status = _text(screen, "#screen-status")
            assert "[REDACTED]" in status
            assert all(secret not in status for secret in secrets)
