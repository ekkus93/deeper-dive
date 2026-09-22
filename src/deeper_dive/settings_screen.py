"""Durable application settings screen."""

from __future__ import annotations

import importlib.util
import shutil
from typing import Protocol, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.model_roles import ModelRole
from deeper_dive.provider_tui import ProviderController


class SettingsApp(Protocol):
    provider_controller: ProviderController

    def action_navigate(self, destination: str) -> None: ...


class SettingsScreen(Screen[None]):
    """Edit production user defaults without hand-editing config.json."""

    ROLE_IDS = {role: f"role-{role.value}" for role in ModelRole}
    DEFAULT_FIELDS = {
        "default_tts_provider": "default-tts-provider",
        "default_tts_voice": "default-tts-voice",
        "research_policy": "research-policy",
        "local_only": "local-only",
        "quick_deep_dive_hosts": "quick-hosts",
        "quick_deep_dive_duration_minutes": "quick-duration",
        "quick_deep_dive_research_policy": "quick-research-policy",
        "log_level": "log-level",
    }

    def __init__(self) -> None:
        super().__init__(id="screen-settings")

    @property
    def settings_app(self) -> SettingsApp:
        return cast(SettingsApp, self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in ("home", "providers", "settings", "help"):
                yield Button(key.title(), id=f"nav-{key}", name=f"nav:{key}")
        with Horizontal(id="project-nav"):
            for key in ("sources", "research", "hosts", "episode", "generate", "library"):
                yield Button(key.title(), id=f"nav-{key}", name=f"nav:{key}")
        with VerticalScroll(id="content"):
            yield Label("Settings", id="screen-title")
            yield Static("Application defaults used by production composition.", id="screen-description")
            yield Button("Manage Providers", id="action-manage-providers", name="nav:providers")
            yield Label("Model role defaults (provider:model)")
            for role in ModelRole:
                yield Input(placeholder=role.value, id=self.ROLE_IDS[role])
            yield Label("Speech defaults")
            yield Input(placeholder="Default TTS provider", id="default-tts-provider")
            yield Input(placeholder="Default TTS voice", id="default-tts-voice")
            yield Label("Research and network policy")
            yield Input(placeholder="Research policy", id="research-policy")
            yield Input(placeholder="Local only: true/false", id="local-only")
            yield Label("Quick Deep Dive defaults")
            yield Input(placeholder="Host presets, comma separated", id="quick-hosts")
            yield Input(placeholder="Target duration minutes", id="quick-duration")
            yield Input(placeholder="Research policy", id="quick-research-policy")
            yield Label("Diagnostics")
            yield Input(placeholder="Log level", id="log-level")
            yield Static("", id="readiness-status")
            yield Button("Save Settings", id="action-save-settings", name="save")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.reload_settings()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name or ""
        if action.startswith("nav:"):
            self.settings_app.action_navigate(action.split(":", 1)[1])
        elif action == "save":
            self.action_save()

    def reload_settings(self) -> None:
        defaults = self.settings_app.provider_controller.config().defaults
        for role, widget_id in self.ROLE_IDS.items():
            self.query_one(f"#{widget_id}", Input).value = defaults.get(role.value, "")
        for key, widget_id in self.DEFAULT_FIELDS.items():
            self.query_one(f"#{widget_id}", Input).value = defaults.get(key, "")
        self.query_one("#readiness-status", Static).update(self._readiness_text())

    def action_save(self) -> None:
        values = {
            role.value: self.query_one(f"#{widget_id}", Input).value
            for role, widget_id in self.ROLE_IDS.items()
        }
        values.update(
            {
                key: self.query_one(f"#{widget_id}", Input).value
                for key, widget_id in self.DEFAULT_FIELDS.items()
            }
        )
        self.settings_app.provider_controller.save_defaults(values)
        self.reload_settings()
        self.query_one("#screen-status", Static).update("Status: Settings saved")

    @staticmethod
    def _readiness_text() -> str:
        ffmpeg = shutil.which("ffmpeg")
        kitten = importlib.util.find_spec("kittentts") is not None
        return "\n".join(
            (
                f"FFmpeg: {'available at ' + ffmpeg if ffmpeg else 'not found'}",
                f"KittenTTS: {'installed' if kitten else 'not installed'}",
                "KittenTTS install/status/benchmark management is available from the provider CLI.",
            )
        )
