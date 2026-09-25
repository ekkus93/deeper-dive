# fmt: off
"""Textual Providers screen."""

from __future__ import annotations

from typing import Protocol, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_errors import user_status

_DEFAULT_TIMEOUT_SECONDS = 60.0
_PROVIDER_FORM_FIELDS = frozenset(
    {
        "base_url",
        "default_model",
        "credential_env",
        "timeout_seconds",
        "network_scope",
        "response_format",
        "voices",
    }
)
_FIELD_LABELS = {
    "base_url": "base URL",
    "default_model": "default model",
    "credential_env": "credential environment variable name",
    "timeout_seconds": "timeout seconds",
    "network_scope": "network scope",
    "response_format": "TTS response format",
    "voices": "voice catalog IDs",
}


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
            yield Input(
                placeholder="Base URL (optional when supported)",
                id="provider-base-url",
            )
            yield Input(
                placeholder="Default model (optional when supported)",
                id="provider-default-model",
            )
            yield Input(
                placeholder="Credential env var name (optional when supported)",
                id="provider-credential-env",
            )
            yield Input(
                placeholder="Timeout seconds (optional when supported; default 60)",
                id="provider-timeout-seconds",
            )
            yield Input(
                placeholder="Network scope: local or remote (optional when supported)",
                id="provider-network-scope",
            )
            yield Input(
                placeholder="TTS response format, e.g. wav/mp3 (optional when supported)",
                id="provider-response-format",
            )
            yield Input(
                placeholder="Voice catalog IDs, comma-separated (optional when supported)",
                id="provider-voices",
            )
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

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "provider-type":
            self.query_one("#provider-details", Static).update(
                self._provider_type_details(event.input.value.strip())
            )

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
            supported_fields = self.provider_app.provider_controller.configuration_fields(provider_type)
            timeout_seconds = self._timeout_seconds(supported_fields)
            self.provider_app.provider_controller.save_provider(
                name,
                provider_type,
                base_url=self._optional_field_value(
                    supported_fields,
                    "base_url",
                    "#provider-base-url",
                ),
                default_model=self._optional_field_value(
                    supported_fields,
                    "default_model",
                    "#provider-default-model",
                ),
                credential_env=self._optional_field_value(
                    supported_fields,
                    "credential_env",
                    "#provider-credential-env",
                ),
                timeout_seconds=timeout_seconds,
                network_scope=self._optional_field_value(
                    supported_fields,
                    "network_scope",
                    "#provider-network-scope",
                ),
                response_format=(
                    self._optional_field_value(
                        supported_fields,
                        "response_format",
                        "#provider-response-format",
                    )
                    or "wav"
                ),
                voices=self._voice_catalog(supported_fields),
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
        self.query_one("#provider-details", Static).update(self._details_text())
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

    def _details_text(self) -> str:
        typed_type = self.query_one("#provider-type", Input).value.strip()
        if typed_type:
            return self._provider_type_details(typed_type)
        if self.selected_provider is None:
            return "Enter a provider adapter to see supported configuration fields."
        provider = self.provider_app.provider_controller.config().providers[self.selected_provider]
        rows = [
            f"Selected: {self.selected_provider}",
            f"Adapter: {provider.provider_type}",
            f"Capability: {self.provider_app.provider_controller.capability(provider.provider_type)}",
            self._provider_type_details(provider.provider_type),
        ]
        if provider.base_url is not None:
            rows.append(f"Base URL: {provider.base_url}")
        if provider.default_model is not None:
            rows.append(f"Default model: {provider.default_model}")
        if provider.credential_env is not None:
            rows.append(f"Credential env var: {provider.credential_env}")
        if provider.network_scope is not None:
            rows.append(f"Network scope: {provider.network_scope}")
        if provider.response_format:
            rows.append(f"Response format: {provider.response_format}")
        if provider.voices:
            rows.append("Voice catalog IDs: " + ", ".join(provider.voices))
        return "\n".join(rows)

    def _provider_type_details(self, provider_type: str) -> str:
        if not provider_type:
            return "Enter a provider adapter to see supported configuration fields."
        try:
            supported_fields = self.provider_app.provider_controller.configuration_fields(provider_type)
        except ValueError as exc:
            return user_status("provider", exc)
        kind = provider_type.strip().lower().replace("_", "-")
        supported = ", ".join(
            _FIELD_LABELS[field]
            for field in sorted(supported_fields)
            if field in _FIELD_LABELS
        )
        ignored = ", ".join(
            _FIELD_LABELS[field]
            for field in sorted(_PROVIDER_FORM_FIELDS - supported_fields)
            if field in _FIELD_LABELS
        )
        rows = [f"Supported optional fields for {kind}: {supported or 'none'}"]
        if ignored:
            rows.append(f"Ignored fields for {kind}: {ignored}")
        return "\n".join(rows)

    def _optional_field_value(
        self, supported_fields: frozenset[str], field: str, selector: str
    ) -> str | None:
        if field not in supported_fields:
            return None
        value = self.query_one(selector, Input).value.strip()
        return value or None

    def _timeout_seconds(self, supported_fields: frozenset[str]) -> float:
        if "timeout_seconds" not in supported_fields:
            return _DEFAULT_TIMEOUT_SECONDS
        raw_value = self.query_one("#provider-timeout-seconds", Input).value.strip()
        if not raw_value:
            return _DEFAULT_TIMEOUT_SECONDS
        try:
            return float(raw_value)
        except ValueError as exc:
            raise ValueError("timeout_seconds must be a number") from exc

    def _voice_catalog(self, supported_fields: frozenset[str]) -> tuple[str, ...]:
        if "voices" not in supported_fields:
            return ()
        raw_value = self.query_one("#provider-voices", Input).value
        return tuple(value.strip() for value in raw_value.split(",") if value.strip())

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
