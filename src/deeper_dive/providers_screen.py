"""Textual Providers screen."""

from __future__ import annotations

from typing import Protocol, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_errors import user_status


class ProviderApp(Protocol):
    provider_controller: ProviderController

    def action_navigate(self, destination: str) -> None: ...


class ProvidersScreen(Screen[None]):
    def __init__(self) -> None:
        super().__init__(id="screen-providers")
        self.selected_provider: str | None = None

    @property
    def provider_app(self) -> ProviderApp:
        return cast(ProviderApp, self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in ("home", "providers", "settings", "help"):
                yield Button(key.title(), id=f"nav-{key}", name=f"nav:{key}")
        with Horizontal(id="project-nav"):
            for key in ("sources", "research", "hosts", "episode", "generate", "library"):
                yield Button(key.title(), id=f"nav-{key}", name=f"nav:{key}")
        with VerticalScroll(id="content"):
            yield Label("Providers", id="screen-title")
            yield Static("Configure language-model and speech providers.", id="screen-description")
            yield Input(placeholder="Config name / runtime provider ID", id="provider-name")
            yield Input(
                placeholder="Adapter: openai, ollama, llama-server, kitten, elevenlabs, ...",
                id="provider-type",
            )
            yield Input(placeholder="Base URL (optional)", id="provider-base-url")
            yield Input(placeholder="Default model (optional)", id="provider-default-model")
            yield Button("Add / Edit", id="action-save-provider", name="save")
            yield Button("Remove", id="action-remove-provider", name="remove")
            yield Button("Test Health", id="action-health-provider", name="health")
            yield Button("Discover Models", id="action-models-provider", name="models")
            yield Button("Discover Voices", id="action-voices-provider", name="voices")
            yield Static("", id="llm-provider-list")
            yield Static("", id="tts-provider-list")
            yield Static("", id="provider-details")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_providers()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name or ""
        if action.startswith("nav:"):
            self.provider_app.action_navigate(action.split(":", 1)[1])
        elif action == "save":
            self.action_save()
        elif action == "remove":
            self.action_remove()
        elif action == "health":
            self.action_health()
        elif action == "models":
            self.action_models()
        elif action == "voices":
            self.action_voices()

    def action_save(self) -> None:
        name = self.query_one("#provider-name", Input).value.strip()
        provider_type = self.query_one("#provider-type", Input).value.strip().lower()
        if not name or not provider_type:
            self._status("Name and concrete provider adapter are required")
            return
        try:
            self.provider_app.provider_controller.save_provider(
                name,
                provider_type,
                base_url=self.query_one("#provider-base-url", Input).value.strip() or None,
                default_model=self.query_one("#provider-default-model", Input).value.strip()
                or None,
            )
        except ValueError as exc:
            self._status(user_status("provider", exc))
            return
        self.selected_provider = name
        self.refresh_providers(f"Saved {provider_type} provider {name}")

    def action_remove(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        self.provider_app.provider_controller.remove_provider(name)
        self.selected_provider = None
        self.refresh_providers(f"Removed provider {name}")

    def action_health(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        kind = self._provider_type(name)
        try:
            if kind == "llm":
                health = self.provider_app.provider_controller.llm(name).health()
                state = "healthy" if health.healthy else "unhealthy"
                self._status(f"{name}: {state} - {health.message}")
            else:
                health = self.provider_app.provider_controller.tts(name).health()
                state = "healthy" if health.healthy else "unhealthy"
                self._status(f"{name}: {state} - {health.message}")
        except (KeyError, RuntimeError, OSError) as exc:
            self._status(f"{name}: {user_status('provider', exc)}")

    def action_models(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        if self._provider_type(name) != "llm":
            self._status(f"{name}: model discovery requires an LLM provider")
            return
        try:
            models = self.provider_app.provider_controller.llm(name).models()
            rows = [
                f"{model.model}: streaming={model.capabilities.streaming}, "
                f"structured={model.capabilities.structured_output}, "
                f"context={model.capabilities.max_context_tokens or 'unknown'}"
                for model in models
            ]
            self.query_one("#provider-details", Static).update("Models:\n" + "\n".join(rows))
            self._status(f"Discovered {len(models)} model(s) for {name}")
        except (KeyError, RuntimeError, OSError) as exc:
            self._status(f"{name}: {user_status('provider', exc)}")

    def action_voices(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        if self._provider_type(name) != "tts":
            self._status(f"{name}: voice discovery requires a TTS provider")
            return
        try:
            voices = self.provider_app.provider_controller.tts(name).voices()
            self.query_one("#provider-details", Static).update(
                "Voices:\n" + "\n".join(f"{voice.name} (id={voice.id})" for voice in voices)
            )
            self._status(f"Discovered {len(voices)} voice(s) for {name}")
        except (KeyError, RuntimeError, OSError) as exc:
            self._status(f"{name}: {user_status('tts', exc)}")

    def refresh_providers(self, status: str = "Ready") -> None:
        providers = self.provider_app.provider_controller.config().providers
        if self.selected_provider not in providers:
            self.selected_provider = next(iter(sorted(providers)), None)
        llm = [
            name
            for name, cfg in sorted(providers.items())
            if self.provider_app.provider_controller.capability(cfg.provider_type) == "llm"
        ]
        tts = [
            name
            for name, cfg in sorted(providers.items())
            if self.provider_app.provider_controller.capability(cfg.provider_type) == "tts"
        ]
        self.query_one("#llm-provider-list", Static).update(self._list_text("LLM providers", llm))
        self.query_one("#tts-provider-list", Static).update(self._list_text("TTS providers", tts))
        self._status(status)

    def _list_text(self, title: str, names: list[str]) -> str:
        rows = [title + ":"]
        rows.extend(f"{'*' if name == self.selected_provider else ' '} {name}" for name in names)
        if not names:
            rows.append("  none")
        return "\n".join(rows)

    def _selected_name(self) -> str | None:
        typed = self.query_one("#provider-name", Input).value.strip()
        name = typed or self.selected_provider
        if name is None or name not in self.provider_app.provider_controller.config().providers:
            self._status("Select or enter a configured provider name")
            return None
        self.selected_provider = name
        return name

    def _provider_type(self, name: str) -> str:
        config = self.provider_app.provider_controller.config().providers[name]
        return self.provider_app.provider_controller.capability(config.provider_type)

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
