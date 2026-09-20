"""Durable application settings screen."""

from __future__ import annotations

from typing import Protocol, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.ffmpeg import FFmpegConfig, FFmpegError
from deeper_dive.model_roles import ModelRole
from deeper_dive.provider_tui import ProviderController


class SettingsApp(Protocol):
    provider_controller: ProviderController

    def action_navigate(self, destination: str) -> None: ...


class SettingsScreen(Screen[None]):
    """Edit non-secret user defaults consumed by production services."""

    @property
    def settings_app(self) -> SettingsApp:
        return cast(SettingsApp, self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in ("home", "providers", "settings", "help"):
                yield Button(key.title(), id=f"nav-{key}", name=f"nav:{key}")
        with Horizontal(id="project-nav"):
            for key in (
                "sources",
                "research",
                "hosts",
                "episode",
                "generate",
                "library",
            ):
                yield Button(key.title(), id=f"nav-{key}", name=f"nav:{key}")
        with VerticalScroll(id="content"):
            yield Label("Settings", id="screen-title")
            yield Static(
                "Durable application defaults (credentials use environment variables)."
            )
            for role in ModelRole:
                yield Input(
                    placeholder="provider:model", id=f"setting-role-{role.value}"
                )
            yield Input(placeholder="Default TTS provider", id="setting-tts-provider")
            yield Input(placeholder="Default TTS voice", id="setting-tts-voice")
            yield Input(placeholder="Research policy", id="setting-research-policy")
            yield Input(placeholder="Local only: true/false", id="setting-local-only")
            yield Input(
                placeholder="Quick hosts, comma separated", id="setting-quick-hosts"
            )
            yield Input(
                placeholder="Quick duration minutes", id="setting-quick-duration"
            )
            yield Input(
                placeholder="Quick research policy", id="setting-quick-research-policy"
            )
            yield Input(placeholder="Logging level", id="setting-log-level")
            yield Button("Save Settings", id="action-save-settings", name="save")
            yield Static("", id="settings-readiness")
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
        for role in ModelRole:
            self.query_one(f"#setting-role-{role.value}", Input).value = defaults.get(
                role.value, ""
            )
        fields = {
            "#setting-tts-provider": "default_tts_provider",
            "#setting-tts-voice": "default_tts_voice",
            "#setting-research-policy": "research_policy",
            "#setting-local-only": "local_only",
            "#setting-quick-hosts": "quick_hosts",
            "#setting-quick-duration": "quick_duration_minutes",
            "#setting-quick-research-policy": "quick_research_policy",
            "#setting-log-level": "log_level",
        }
        for selector, key in fields.items():
            self.query_one(selector, Input).value = defaults.get(key, "")
        self.query_one("#settings-readiness", Static).update(self._readiness())

    def action_save(self) -> None:
        defaults: dict[str, str] = {}
        for role in ModelRole:
            value = self.query_one(f"#setting-role-{role.value}", Input).value.strip()
            if value:
                if ":" not in value:
                    self._status(f"{role.value} must use provider:model")
                    return
                defaults[role.value] = value
        fields = {
            "#setting-tts-provider": "default_tts_provider",
            "#setting-tts-voice": "default_tts_voice",
            "#setting-research-policy": "research_policy",
            "#setting-local-only": "local_only",
            "#setting-quick-hosts": "quick_hosts",
            "#setting-quick-duration": "quick_duration_minutes",
            "#setting-quick-research-policy": "quick_research_policy",
            "#setting-log-level": "log_level",
        }
        for selector, key in fields.items():
            value = self.query_one(selector, Input).value.strip()
            if value:
                defaults[key] = value
        duration = defaults.get("quick_duration_minutes")
        if duration:
            try:
                if float(duration) <= 0:
                    raise ValueError
            except ValueError:
                self._status("Quick duration must be a positive number")
                return
        config = self.settings_app.provider_controller.config()
        config.defaults = defaults
        self.settings_app.provider_controller.config_store.save(config)
        self.reload_settings()
        self._status("Settings saved")

    @staticmethod
    def _readiness() -> str:
        try:
            ffmpeg = FFmpegConfig.detect()
            ffmpeg_status = f"FFmpeg: ready ({ffmpeg.executable})"
        except FFmpegError:
            ffmpeg_status = "FFmpeg: unavailable"
        return f"{ffmpeg_status}\nKittenTTS: manage through Providers (adapter: kitten)"

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
