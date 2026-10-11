"""Production Textual provider forms preserve state on failed configuration writes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfigStore


def test_provider_save_failure_preserves_form_and_sanitizes_error(tmp_path: Path) -> None:
    asyncio.run(_provider_save_failure_preserves_form_and_sanitizes_error(tmp_path))


async def _provider_save_failure_preserves_form_and_sanitizes_error(tmp_path: Path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    controller = ProviderController(store, LLMProviderRegistry(), {})
    app = DeeperDiveApp(
        DeeperDiveService(WorkspaceManager(tmp_path / "data")),
        provider_controller=controller,
    )
    canary = "provider-persistence-canary"
    endpoint = f"https://example.test/v1?api%5Fkey={canary}"

    def fail_save(self: ProviderController, *args: object, **kwargs: object) -> None:
        _ = (self, args, kwargs)
        raise OSError(f"failed provider config write to {endpoint}")

    async with app.run_test(size=(110, 34)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ProvidersScreen)
        screen.query_one("#provider-name", Input).value = "remote"
        screen.query_one("#provider-type", Input).value = "openai"
        screen.query_one("#provider-base-url", Input).value = "https://example.test/v1"

        with patch.object(ProviderController, "save_provider", fail_save):
            screen.action_save()
        await pilot.pause()

        assert app.screen is screen
        assert screen.query_one("#provider-name", Input).value == "remote"
        assert screen.query_one("#provider-base-url", Input).value == "https://example.test/v1"
        assert "remote" not in controller.config().providers
        status = str(screen.query_one("#screen-status", Static).render())
        assert "Provider request failed." in status
        assert "[REDACTED]" in status
        assert canary not in status


def test_provider_remove_failure_keeps_selected_provider(tmp_path: Path) -> None:
    asyncio.run(_provider_remove_failure_keeps_selected_provider(tmp_path))


async def _provider_remove_failure_keeps_selected_provider(tmp_path: Path) -> None:
    store = UserConfigStore(tmp_path / "config.json")
    controller = ProviderController(store, LLMProviderRegistry(), {})
    controller.save_provider("local", "fake", default_model="fake-v1")
    app = DeeperDiveApp(
        DeeperDiveService(WorkspaceManager(tmp_path / "data")),
        provider_controller=controller,
    )

    def fail_remove(self: ProviderController, name: str) -> None:
        _ = (self, name)
        raise OSError("read-only user configuration")

    async with app.run_test(size=(110, 34)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ProvidersScreen)
        screen.query_one("#provider-name", Input).value = "local"
        screen.action_remove()
        with patch.object(ProviderController, "remove_provider", fail_remove):
            screen.action_confirm_remove()
        await pilot.pause()

        assert app.screen is screen
        assert "local" in controller.config().providers
        assert screen.selected_provider == "local"
        status = str(screen.query_one("#screen-status", Static).render())
        assert "Provider request failed." in status
