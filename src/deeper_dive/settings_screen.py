"""Durable application settings screen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(slots=True)
class SettingsController:
    """Persist non-secret application defaults through the production config store."""

    provider_controller: ProviderController

    def set_default(self, key: str, value: str) -> None:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("settings key is required")
        config = self.provider_controller.config()
        normalized_value = value.strip()
        if normalized_value:
            config.defaults[normalized_key] = normalized_value
        else:
            config.defaults.pop(normalized_key, None)
        self.provider_controller.config_store.save(config)

    def save_model_default(self, role: str, provider_model: str) -> None:
        role_key = ModelRole(role.strip()).value
        if provider_model.strip() and ":" not in provider_model:
            raise ValueError("model default must use provider:model")
        self.set_default(role_key, provider_model)

    def save_tts_defaults(self, provider: str, voice: str) -> None:
        self.set_default("tts_provider", provider)
        self.set_default("tts_voice", voice)

    def save_research_defaults(self, policy: str, network_policy: str) -> None:
        self.set_default("research_policy", policy)
        self.set_default("network_policy", network_policy)

    def save_quick_deep_dive_defaults(
        self,
        duration_minutes: str,
        host_presets: str,
        research_policy: str,
    ) -> None:
        if duration_minutes.strip():
            minutes = int(duration_minutes)
            if minutes <= 0:
                raise ValueError("Quick Deep Dive duration must be positive")
        self.set_default("quick_deep_dive_duration_minutes", duration_minutes)
        self.set_default("quick_deep_dive_host_presets", host_presets)
        self.set_default("quick_deep_dive_research_policy", research_policy)

    def save_runtime_defaults(
        self,
        ffmpeg_executable: str,
        kitten_model_dir: str,
        diagnostic_logging: str,
    ) -> None:
        self.set_default("ffmpeg_executable", ffmpeg_executable)
        self.set_default("kitten_model_dir", kitten_model_dir)
        self.set_default("diagnostic_logging", diagnostic_logging)

    def summary(self) -> tuple[str, ...]:
        defaults = self.provider_controller.config().defaults
        quick_duration = defaults.get("quick_deep_dive_duration_minutes", "20")
        quick_hosts = defaults.get(
            "quick_deep_dive_host_presets",
            "curious_explainer,skeptic",
        )
        quick_research = defaults.get("quick_deep_dive_research_policy", "useful")
        rows = ["Model role defaults:"]
        for role in ModelRole:
            rows.append(f"  {role.value}: {defaults.get(role.value, 'unassigned')}")
        rows.extend(
            (
                "TTS defaults:",
                f"  provider: {defaults.get('tts_provider', 'unassigned')}",
                f"  voice: {defaults.get('tts_voice', 'unassigned')}",
                "Research/network defaults:",
                f"  research_policy: {defaults.get('research_policy', 'useful')}",
                f"  network_policy: {defaults.get('network_policy', 'configured providers')}",
                f"  local_only: {defaults.get('local_only', 'false')}",
                "Quick Deep Dive defaults:",
                f"  duration_minutes: {quick_duration}",
                f"  host_presets: {quick_hosts}",
                f"  research_policy: {quick_research}",
                "Runtime/readiness defaults:",
                f"  ffmpeg_executable: {defaults.get('ffmpeg_executable', 'auto-detect')}",
                f"  kitten_model_dir: {defaults.get('kitten_model_dir', 'default models dir')}",
                f"  diagnostic_logging: {defaults.get('diagnostic_logging', 'normal')}",
            )
        )
        return tuple(rows)


class SettingsScreen(Screen[None]):
    """Durable settings and defaults management."""

    def __init__(self) -> None:
        super().__init__(id="screen-settings")

    @property
    def settings_app(self) -> SettingsApp:
        return cast(SettingsApp, self.app)

    @property
    def controller(self) -> SettingsController:
        return SettingsController(self.settings_app.provider_controller)

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
            yield Static(
                "Configure durable defaults consumed by preflight, planning, providers, "
                "Quick Deep Dive, and diagnostics.",
                id="screen-description",
            )
            yield Static("", id="settings-summary")
            yield Input(placeholder="Default key", id="settings-key")
            yield Input(placeholder="Default value; blank removes key", id="settings-value")
            yield Button("Save Default", id="action-save-default", name="save-default")
            yield Input(placeholder="Model role, e.g. episode_planning", id="model-role")
            yield Input(placeholder="provider:model", id="model-assignment")
            yield Button("Save Model Default", id="action-save-model", name="save-model")
            yield Input(placeholder="Default TTS provider", id="tts-provider")
            yield Input(placeholder="Default TTS voice", id="tts-voice")
            yield Button("Save TTS Defaults", id="action-save-tts", name="save-tts")
            yield Input(placeholder="Research policy", id="research-policy")
            yield Input(placeholder="Network policy", id="network-policy")
            yield Button("Save Research Defaults", id="action-save-research", name="save-research")
            yield Input(placeholder="Quick Deep Dive duration minutes", id="quick-duration")
            yield Input(placeholder="Quick Deep Dive host presets", id="quick-hosts")
            yield Input(placeholder="Quick Deep Dive research policy", id="quick-research")
            yield Button("Save Quick Defaults", id="action-save-quick", name="save-quick")
            yield Input(placeholder="FFmpeg executable override", id="ffmpeg-executable")
            yield Input(placeholder="KittenTTS model directory", id="kitten-model-dir")
            yield Input(placeholder="Diagnostic logging preference", id="diagnostic-logging")
            yield Button("Save Runtime Defaults", id="action-save-runtime", name="save-runtime")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_settings()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name or ""
        if action.startswith("nav:"):
            self.settings_app.action_navigate(action.split(":", 1)[1])
        elif action == "save-default":
            self.action_save_default()
        elif action == "save-model":
            self.action_save_model_default()
        elif action == "save-tts":
            self.action_save_tts_defaults()
        elif action == "save-research":
            self.action_save_research_defaults()
        elif action == "save-quick":
            self.action_save_quick_defaults()
        elif action == "save-runtime":
            self.action_save_runtime_defaults()

    def action_save_default(self) -> None:
        self._save(
            lambda: self.controller.set_default(
                self.query_one("#settings-key", Input).value,
                self.query_one("#settings-value", Input).value,
            ),
            "Saved default",
        )

    def action_save_model_default(self) -> None:
        self._save(
            lambda: self.controller.save_model_default(
                self.query_one("#model-role", Input).value,
                self.query_one("#model-assignment", Input).value,
            ),
            "Saved model default",
        )

    def action_save_tts_defaults(self) -> None:
        self._save(
            lambda: self.controller.save_tts_defaults(
                self.query_one("#tts-provider", Input).value,
                self.query_one("#tts-voice", Input).value,
            ),
            "Saved TTS defaults",
        )

    def action_save_research_defaults(self) -> None:
        self._save(
            lambda: self.controller.save_research_defaults(
                self.query_one("#research-policy", Input).value,
                self.query_one("#network-policy", Input).value,
            ),
            "Saved research defaults",
        )

    def action_save_quick_defaults(self) -> None:
        self._save(
            lambda: self.controller.save_quick_deep_dive_defaults(
                self.query_one("#quick-duration", Input).value,
                self.query_one("#quick-hosts", Input).value,
                self.query_one("#quick-research", Input).value,
            ),
            "Saved Quick Deep Dive defaults",
        )

    def action_save_runtime_defaults(self) -> None:
        self._save(
            lambda: self.controller.save_runtime_defaults(
                self.query_one("#ffmpeg-executable", Input).value,
                self.query_one("#kitten-model-dir", Input).value,
                self.query_one("#diagnostic-logging", Input).value,
            ),
            "Saved runtime defaults",
        )

    def refresh_settings(self, status: str = "Ready") -> None:
        self.query_one("#settings-summary", Static).update(
            "Current settings:\n" + "\n".join(self.controller.summary())
        )
        self._status(status)

    def _save(self, operation: Callable[[], None], success: str) -> None:
        try:
            operation()
        except (TypeError, ValueError) as exc:
            self._status(str(exc))
            return
        self.refresh_settings(success)

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
