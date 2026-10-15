"""Form hydration, readiness plumbing and preset helpers for the first-run wizard."""

from __future__ import annotations

from typing import cast

from textual.css.query import NoMatches
from textual.widgets import Button, Input, Select

from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunRuntimeSnapshot,
)
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_workflow import CompletionProbe, WizardContext, WizardKind
from deeper_dive.model_roles import ModelRole
from deeper_dive.settings_screen import SettingsController
from deeper_dive.wizard_shell_variants import FirstRunWizardShell


class FirstRunFormControls(FirstRunWizardShell):
    """Form hydration, readiness plumbing and preset helpers for the first-run wizard."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe)
        self._llm_provider_name: str | None = None
        # Steps whose baseline was captured from durable values before a preset
        # overwrote the controls; arriving at the step must not re-baseline them.
        self._preset_baseline_steps: set[str] = set()
        self._tts_provider_name: str | None = None
        self._model_test_identity: str | None = None
        self._model_test_summary = "Run a synthetic model test before continuing."
        self._model_options: tuple[tuple[str, str], ...] = ()
        self._voice_options: tuple[tuple[str, str], ...] = ()
        # Select.Changed can arrive after a saved selection is hydrated. Track
        # the actual choice so initial/stale events cannot reset durable fields.
        self._last_llm_choice: str | None = None
        self._last_speech_choice: str | None = None

    @property
    def settings(self) -> SettingsController:
        return SettingsController(self.context.composition.provider_controller)

    @property
    def _runtime_readiness(self) -> FirstRunReadinessCoordinator | None:
        return cast(
            FirstRunReadinessCoordinator | None,
            getattr(self.app, "_first_run_readiness", None),
        )

    def _runtime_snapshot(self) -> FirstRunRuntimeSnapshot | None:
        coordinator = self._runtime_readiness
        return coordinator.snapshot if coordinator is not None else None

    def _request_runtime_readiness(self) -> None:
        coordinator = self._runtime_readiness
        if coordinator is not None:
            coordinator.request(self.app, self._runtime_readiness_updated)

    def _runtime_readiness_updated(self) -> None:
        recovered = self.navigator.recovered_state()
        if recovered != self.context.state:
            if self._current_form_dirty():
                # A late probe can invalidate an earlier prerequisite. Do not
                # relocate the wizard while its current form contains unsaved
                # edits; the user must explicitly save or discard first.
                self.set_status(
                    "Readiness changed; unsaved setup edits remain. "
                    "Save or discard them before changing steps."
                )
            else:
                self.context.state = recovered
        self._sync_text(preserve_status=True)
        self._sync_setup_controls()

    def _checking_text(self) -> str:
        coordinator = self._runtime_readiness
        if coordinator is not None and coordinator.view.state == "failed":
            message = coordinator.view.message or "provider check failed"
            if "retry" not in message.casefold():
                message += " Review provider settings and retry."
            return "Readiness check needs attention: " + message
        return "Checking provider and local runtime readiness…"

    def _clear_completed_setup_draft(self) -> None:
        """A terminal first-run setup must not leave a stale resume checkpoint."""
        if self.completion_probe("ready"):
            data_dir = self.context.composition.service.workspaces.data_dir
            GuidedDraftStore(data_dir).clear(WizardKind.FIRST_RUN)

    def _load_existing_setup(self) -> None:
        controller = self.context.composition.provider_controller
        config = controller.config()
        llm_names = [
            name
            for name, provider in sorted(config.providers.items())
            if controller.capability(provider.provider_type) == "llm"
        ]
        if llm_names:
            if self._llm_provider_name not in llm_names:
                self._llm_provider_name = llm_names[0]
            provider = config.providers[self._llm_provider_name]
            self.query_one("#setup-provider-name", Input).value = self._llm_provider_name
            self.query_one("#setup-provider-adapter", Input).value = provider.provider_type
            self.query_one("#setup-provider-base-url", Input).value = provider.base_url or ""
            self.query_one("#setup-provider-model", Input).value = provider.default_model or ""
            self.query_one("#setup-provider-credential-env", Input).value = (
                provider.credential_env or ""
            )
            self.query_one("#setup-provider-network", Input).value = provider.network_scope or ""
            choice = self._choice_for_adapter(provider.provider_type, provider.base_url)
            ai_choice = self.query_one("#setup-ai-choice", Select)
            with ai_choice.prevent(Select.Changed):
                ai_choice.value = choice

        tts_names = [
            name
            for name, provider in sorted(config.providers.items())
            if controller.capability(provider.provider_type) == "tts"
        ]
        selected_tts = config.defaults.get("tts_provider")
        self._tts_provider_name = (
            selected_tts if selected_tts in tts_names else (tts_names[0] if tts_names else None)
        )
        if self._tts_provider_name:
            provider = config.providers[self._tts_provider_name]
            self.query_one("#setup-speech-name", Input).value = self._tts_provider_name
            self.query_one("#setup-speech-adapter", Input).value = provider.provider_type
            self.query_one("#setup-speech-base-url", Input).value = provider.base_url or ""
            self.query_one("#setup-speech-model", Input).value = provider.default_model or ""
            self.query_one("#setup-speech-credential-env", Input).value = (
                provider.credential_env or ""
            )
            self.query_one("#setup-speech-network", Input).value = provider.network_scope or ""
            self.query_one("#setup-speech-voices", Input).value = ",".join(provider.voices)
            speech_choice = (
                provider.provider_type
                if provider.provider_type in {"kitten", "openai-tts", "elevenlabs"}
                else "advanced"
            )
            speech_select = self.query_one("#setup-speech-choice", Select)
            with speech_select.prevent(Select.Changed):
                speech_select.value = speech_choice
        elif config.defaults.get("speech_setup") == "deferred":
            speech_select = self.query_one("#setup-speech-choice", Select)
            with speech_select.prevent(Select.Changed):
                speech_select.value = "deferred"

        defaults = config.defaults
        duration = defaults.get("quick_deep_dive_duration_minutes", "20")
        if duration in {"10", "20", "30"}:
            duration_select = self.query_one("#setup-duration", Select)
            with duration_select.prevent(Select.Changed):
                duration_select.value = duration
        research = defaults.get("research_policy", "useful")
        if research in {"off", "useful", "aggressive"}:
            research_select = self.query_one("#setup-research-default", Select)
            with research_select.prevent(Select.Changed):
                research_select.value = research
        for role, selector in (
            (ModelRole.EPISODE_PLANNING, "#setup-role-episode-planning"),
            (ModelRole.HOST_GENERATION, "#setup-role-host-generation"),
            (ModelRole.DIRECTING, "#setup-role-directing"),
            (ModelRole.VERIFICATION, "#setup-role-verification"),
        ):
            self.query_one(selector, Input).value = defaults.get(role.value, "")

    def _sync_setup_controls(self) -> None:
        step = self.context.state.current_step
        visible_ids = {
            "ai-provider": {"#setup-ai-choice"},
            "provider-config": {
                "#setup-provider-name",
                "#setup-provider-adapter",
                "#setup-provider-base-url",
                "#setup-provider-model",
                "#setup-provider-credential-env",
                "#setup-provider-network",
                "#setup-discover-models",
                "#setup-model-picker",
                "#setup-save-provider",
                "#setup-test-provider",
            },
            "model-test": {
                "#setup-run-model-test",
                "#setup-recommended-roles",
                "#setup-role-episode-planning",
                "#setup-role-host-generation",
                "#setup-role-directing",
                "#setup-role-verification",
                "#setup-save-roles",
            },
            "speech": {
                "#setup-speech-choice",
                "#setup-speech-name",
                "#setup-speech-adapter",
                "#setup-speech-base-url",
                "#setup-speech-model",
                "#setup-speech-credential-env",
                "#setup-speech-network",
                "#setup-speech-voices",
                "#setup-save-speech",
            },
            "voice-defaults": {
                "#setup-discover-voices",
                "#setup-host1-voice",
                "#setup-host2-voice",
                "#setup-preview-voice",
                "#setup-duration",
                "#setup-research-default",
                "#setup-save-defaults",
            },
            "ready": {"#setup-ready-new", "#setup-ready-home"},
        }
        for readiness_step in (
            "system-check",
            "ai-provider",
            "provider-config",
            "model-test",
            "speech",
            "voice-defaults",
            "ready",
        ):
            visible_ids.setdefault(readiness_step, set()).add("#setup-retry-readiness")
        all_ids = set().union(*visible_ids.values())
        shown = visible_ids.get(step, set())
        for selector in all_ids:
            self.query_one(selector).display = selector in shown

        if step == "provider-config":
            # Refreshing controls must not refill a field deliberately cleared
            # by the user. Initial entry still applies the selected preset.
            if step not in self._form_baselines or not self._current_form_dirty():
                self._apply_llm_choice_defaults(force=False)
            manual = self._select_value("#setup-ai-choice") == "manual"
            self.query_one("#setup-provider-adapter", Input).display = manual
            adapter = self._selected_llm_adapter()
            controller = self.context.composition.provider_controller
            fields = (
                controller.configuration_fields(adapter)
                if controller.capability(adapter) == "llm"
                else frozenset()
            )
            for selector, field in (
                ("#setup-provider-base-url", "base_url"),
                ("#setup-provider-model", "default_model"),
                ("#setup-provider-credential-env", "credential_env"),
                ("#setup-provider-network", "network_scope"),
            ):
                self.query_one(selector, Input).display = field in fields
            self.query_one("#setup-model-picker", Select).display = "default_model" in fields
            self.query_one("#setup-discover-models", Button).display = "default_model" in fields
        if step == "model-test":
            advanced = self.context.state.setup_mode is not None and (
                self.context.state.setup_mode.value == "advanced"
            )
            self.query_one("#setup-recommended-roles", Button).display = not advanced
            for selector in (
                "#setup-role-episode-planning",
                "#setup-role-host-generation",
                "#setup-role-directing",
                "#setup-role-verification",
                "#setup-save-roles",
            ):
                self.query_one(selector).display = advanced
        if step == "speech":
            # Refreshing controls must not refill a field deliberately cleared
            # by the user. Initial entry still applies the selected preset.
            if step not in self._form_baselines or not self._current_form_dirty():
                self._apply_speech_choice_defaults(force=False)
            choice = self._select_value("#setup-speech-choice")
            custom = choice == "advanced"
            deferred = choice == "deferred"
            adapter = (
                self.query_one("#setup-speech-adapter", Input).value.strip()
                if custom
                else (choice or "")
            )
            controller = self.context.composition.provider_controller
            fields = (
                controller.configuration_fields(adapter)
                if controller.capability(adapter) == "tts"
                else frozenset()
            )
            self.query_one("#setup-speech-adapter", Input).display = custom
            self.query_one("#setup-speech-name", Input).display = not deferred
            for selector, field in (
                ("#setup-speech-base-url", "base_url"),
                ("#setup-speech-model", "default_model"),
                ("#setup-speech-credential-env", "credential_env"),
                ("#setup-speech-network", "network_scope"),
                ("#setup-speech-voices", "voices"),
            ):
                self.query_one(selector, Input).display = not deferred and field in fields

    def _capture_preset_baseline(self, step: str) -> None:
        """Record the durable (pre-preset) values of ``step`` as its clean baseline.

        A preset the user picks overwrites the provider controls. Those values are
        unsaved edits relative to the stored provider, so they must not become the
        baseline when the wizard later arrives at ``step``.
        """
        if step in self._preset_baseline_steps:
            return
        current = self._editable_snapshot(step)
        stored = self._form_baselines.get(step)
        if stored is not None and stored != current:
            return  # The user already edited this step; keep that baseline.
        self._form_baselines[step] = current
        self._form_baseline_targets[step] = (
            self.context.project_id,
            self.context.episode_id,
            self._llm_provider_name,
        )
        self._preset_baseline_steps.add(step)

    def _remember_current_form(self) -> None:
        self._preset_baseline_steps.discard(self.context.state.current_step)
        super()._remember_current_form()

    def _apply_llm_choice_defaults(self, *, force: bool) -> None:
        choice = self._select_value("#setup-ai-choice") or "ollama"
        presets = {
            "ollama": ("ollama", "ollama", "http://127.0.0.1:11434", "local"),
            "llama-server": (
                "llama-server",
                "llama-server",
                "http://127.0.0.1:8080",
                "local",
            ),
            "openai": ("openai", "openai", "", "remote"),
            "openai-compatible": ("compatible", "openai", "", "remote"),
            "manual": ("", "", "", ""),
        }
        name, adapter, base_url, scope = presets[choice]
        for selector, value in (
            ("#setup-provider-name", name),
            ("#setup-provider-adapter", adapter),
            ("#setup-provider-base-url", base_url),
            ("#setup-provider-network", scope),
        ):
            widget = self.query_one(selector, Input)
            if force or not widget.value:
                widget.value = value

    def _apply_speech_choice_defaults(self, *, force: bool) -> None:
        choice = self._select_value("#setup-speech-choice") or "kitten"
        presets = {
            "kitten": ("speech", "kitten", "", "local"),
            "openai-tts": ("speech", "openai-tts", "", "remote"),
            "elevenlabs": ("speech", "elevenlabs", "", "remote"),
            "advanced": ("speech", "", "", ""),
            "deferred": ("", "", "", ""),
        }
        name, adapter, base_url, scope = presets[choice]
        for selector, value in (
            ("#setup-speech-name", name),
            ("#setup-speech-adapter", adapter),
            ("#setup-speech-base-url", base_url),
            ("#setup-speech-network", scope),
        ):
            widget = self.query_one(selector, Input)
            if force or not widget.value:
                widget.value = value

    def _selected_llm_adapter(self) -> str:
        choice = self._select_value("#setup-ai-choice") or "ollama"
        if choice == "openai-compatible":
            return "openai"
        if choice == "manual":
            return self.query_one("#setup-provider-adapter", Input).value.strip()
        return choice

    def _selected_llm_name(self) -> str | None:
        typed = self.query_one("#setup-provider-name", Input).value.strip()
        if typed:
            config = self.context.composition.provider_controller.config()
            if typed in config.providers:
                self._llm_provider_name = typed
        return self._llm_provider_name

    def _selected_tts_name(self) -> str | None:
        config = self.context.composition.provider_controller.config()
        configured = config.defaults.get("tts_provider", "").strip()
        if configured and configured in config.providers:
            self._tts_provider_name = configured
        return self._tts_provider_name

    def _current_llm_identity(self) -> str | None:
        name = self._selected_llm_name()
        if name is None:
            return None
        config = self.context.composition.provider_controller.config().providers.get(name)
        if config is None or not config.default_model:
            return None
        return f"{name}:{config.default_model}"

    def _optional_input(self, selector: str) -> str | None:
        raw = self.query_one(selector, Input).value
        if any(ord(character) < 32 or ord(character) == 127 for character in raw):
            raise ValueError("Optional provider settings must be single-line.")
        value = raw.strip()
        return value or None

    def _select_value(self, selector: str) -> str | None:
        # Compose can render a resumed step before its controls are mounted.
        # A missing Select is not a user choice and must not crash startup.
        try:
            value = self.query_one(selector, Select).value
        except NoMatches:
            return None
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _choice_for_adapter(adapter: str, base_url: str | None) -> str:
        normalized = adapter.strip().lower().replace("_", "-")
        if normalized == "openai" and base_url and "api.openai.com" not in base_url:
            return "openai-compatible"
        if normalized in {"ollama", "llama-server", "openai"}:
            return normalized
        return "manual"
