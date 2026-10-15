"""Production-backed first-run setup workflow."""

from __future__ import annotations

from time import monotonic
from typing import Protocol, cast

from textual.widget import Widget
from textual.widgets import Button, Input, Select

from deeper_dive.diagnostics import redact
from deeper_dive.guided_first_run_speech import FirstRunSpeechActions
from deeper_dive.llm import LLMMessage, LLMRequest
from deeper_dive.model_roles import ModelRole
from deeper_dive.wizard_transitions import Transition, TransitionKind, WizardSaveResult

_REQUIRED_SETUP_ROLES = (
    ModelRole.EPISODE_PLANNING,
    ModelRole.HOST_GENERATION,
    ModelRole.DIRECTING,
    ModelRole.VERIFICATION,
)


class _NavigationApp(Protocol):
    def action_navigate(self, destination: str) -> None: ...


class GuidedFirstRunWizard(FirstRunSpeechActions):
    """Complete first-run flow routed through durable provider/settings boundaries."""

    def _wizard_target(self, step: str) -> str | None:
        if step == "provider-config":
            return self._llm_provider_name
        if step == "speech":
            return self._tts_provider_name
        return super()._wizard_target(step)

    def _save_dirty_step(self) -> WizardSaveResult:
        step = self.context.state.current_step
        self._last_form_status = ""
        if step == "provider-config":
            return WizardSaveResult.from_bool(self.action_save_provider())
        if step == "model-test":
            return WizardSaveResult.from_bool(self.action_save_roles())
        if step == "speech":
            return WizardSaveResult.from_bool(self.action_save_speech())
        if step == "voice-defaults":
            return WizardSaveResult.from_bool(self.action_save_defaults())
        return super()._save_dirty_step()

    def action_retry_readiness(self) -> None:
        """Retry the shared bounded provider readiness probe."""
        if self.busy or self._exit_confirmation_pending:
            return
        coordinator = self._runtime_readiness
        if coordinator is None:
            self.set_status("Provider readiness is unavailable.")
            return
        coordinator.request(self.app, self._runtime_readiness_updated, user_initiated=True)
        self._sync_text()
        if coordinator.snapshot is None:
            self.set_status(self._checking_text())

    def step_controls(self) -> tuple[Widget, ...]:
        return (
            *super().step_controls(),
            Button("Retry Readiness", id="setup-retry-readiness", name="retry-readiness"),
            Select(
                [
                    ("Ollama — local", "ollama"),
                    ("llama-server — local", "llama-server"),
                    ("OpenAI — cloud", "openai"),
                    ("OpenAI-compatible API", "openai-compatible"),
                    ("Manual / advanced", "manual"),
                ],
                value="ollama",
                allow_blank=False,
                id="setup-ai-choice",
            ),
            Input(placeholder="Provider name", id="setup-provider-name"),
            Input(placeholder="Concrete adapter", id="setup-provider-adapter"),
            Input(placeholder="Base URL", id="setup-provider-base-url"),
            Input(placeholder="Model", id="setup-provider-model"),
            Input(
                placeholder="Credential environment variable name",
                id="setup-provider-credential-env",
            ),
            Input(placeholder="Network scope: local or remote", id="setup-provider-network"),
            Button("Discover Models", id="setup-discover-models", name="discover-models"),
            Select([], allow_blank=True, id="setup-model-picker"),
            Button("Save Provider", id="setup-save-provider", name="save-provider"),
            Button("Test Connection", id="setup-test-provider", name="test-provider"),
            Button("Run Synthetic Model Test", id="setup-run-model-test", name="run-model-test"),
            Button("Use Recommended Roles", id="setup-recommended-roles", name="recommended-roles"),
            Input(placeholder="episode_planning provider:model", id="setup-role-episode-planning"),
            Input(placeholder="host_generation provider:model", id="setup-role-host-generation"),
            Input(placeholder="directing provider:model", id="setup-role-directing"),
            Input(placeholder="verification provider:model", id="setup-role-verification"),
            Button("Save Role Assignments", id="setup-save-roles", name="save-roles"),
            Select(
                [
                    ("KittenTTS — local", "kitten"),
                    ("OpenAI TTS — cloud", "openai-tts"),
                    ("ElevenLabs — cloud", "elevenlabs"),
                    ("No speech yet", "deferred"),
                    ("Advanced / Custom", "advanced"),
                ],
                value="kitten",
                allow_blank=False,
                id="setup-speech-choice",
            ),
            Input(placeholder="Speech provider name", id="setup-speech-name"),
            Input(placeholder="Speech adapter", id="setup-speech-adapter"),
            Input(placeholder="Speech base URL", id="setup-speech-base-url"),
            Input(placeholder="Speech model", id="setup-speech-model"),
            Input(
                placeholder="Speech credential environment variable name",
                id="setup-speech-credential-env",
            ),
            Input(placeholder="Speech network scope: local or remote", id="setup-speech-network"),
            Input(
                placeholder="Custom voice IDs, comma-separated",
                id="setup-speech-voices",
            ),
            Button("Save Speech Choice", id="setup-save-speech", name="save-speech"),
            Button("Discover Voices", id="setup-discover-voices", name="discover-voices"),
            Select([], allow_blank=True, id="setup-host1-voice"),
            Select([], allow_blank=True, id="setup-host2-voice"),
            Button("Preview Host 1 Voice", id="setup-preview-voice", name="preview-voice"),
            Select(
                [("10 minutes", "10"), ("20 minutes", "20"), ("30 minutes", "30")],
                value="20",
                allow_blank=False,
                id="setup-duration",
            ),
            Select(
                [
                    ("Use only my sources", "off"),
                    ("Fill important gaps", "useful"),
                    ("Research extensively", "aggressive"),
                ],
                value="useful",
                allow_blank=False,
                id="setup-research-default",
            ),
            Button("Save Voice & Defaults", id="setup-save-defaults", name="save-defaults"),
            Button(
                "Create My First Deep Dive",
                id="setup-ready-new",
                name="ready-new",
            ),
            Button("Go to Dashboard", id="setup-ready-home", name="ready-home"),
        )

    def step_content(self, step_key: str) -> str:
        if step_key == "welcome":
            return super().step_content(step_key)
        if step_key == "system-check":
            snapshot = self._runtime_snapshot()
            if snapshot is None:
                return self._checking_text()
            check = snapshot.system_check
            rows = list(check.summary())
            if getattr(self, "_system_details_visible", False):
                rows.extend(("", "Details:", *check.diagnostics))
                rows.append(
                    "Remediation: choose any healthy supported provider. "
                    "Install FFmpeg before audio generation."
                )
            return "\n".join(rows)
        if step_key == "ai-provider":
            snapshot = self._runtime_snapshot()
            if snapshot is None:
                return self._checking_text()
            check = snapshot.system_check
            detected = []
            if check.ollama_reachable:
                detected.append("Ollama")
            if check.llama_server_reachable:
                detected.append("llama-server")
            recommendation = detected[0] if detected else "no local provider detected"
            return (
                "Choose the language-model provider used by production planning and generation.\n"
                f"Detected local providers: {', '.join(detected) if detected else 'none'}.\n"
                f"Quick Setup recommendation: {recommendation}. "
                "Cloud choices disclose credential and network requirements before save."
            )
        if step_key == "provider-config":
            choice = self._select_value("#setup-ai-choice") or "ollama"
            return (
                f"Configure {choice}. Only adapter-supported fields are persisted. "
                "Credentials are referenced by environment-variable name; credential values "
                "are never stored. Save uses the same transactional provider build boundary "
                "as the advanced Providers screen."
            )
        if step_key == "model-test":
            return (
                "Test the selected production provider with a small synthetic prompt; no user "
                "source content is sent.\n" + self._model_test_summary
            )
        if step_key == "speech":
            return (
                "Choose speech. Local KittenTTS stays on-device; OpenAI TTS and ElevenLabs "
                "use remote services and require credential references. 'No speech yet' is "
                "valid setup but will remain audio-not-ready at generation time."
            )
        if step_key == "voice-defaults":
            return (
                "Choose friendly voices for Host 1 and Host 2, then select default episode "
                "duration and research level. Voice IDs remain technical details, not the "
                "primary user label."
            )
        if step_key == "ready":
            snapshot = self._runtime_snapshot()
            if snapshot is None:
                return self._checking_text()
            ready = snapshot.readiness
            return "\n".join(
                (
                    f"Language model: {'Ready' if ready.llm_provider_ready else 'Needs attention'}",
                    f"Model roles: {'Ready' if ready.model_roles_ready else 'Needs attention'}",
                    (
                        "Speech: intentionally deferred"
                        if ready.speech_deferred
                        else f"Speech/audio: {'Ready' if ready.audio_ready else 'Needs attention'}"
                    ),
                    f"FFmpeg: {'Ready' if ready.ffmpeg_available else 'Not available'}",
                    f"Defaults: {'Ready' if ready.defaults_ready else 'Needs attention'}",
                )
            )
        return super().step_content(step_key)

    def on_mount(self) -> None:
        super().on_mount()
        self._load_existing_setup()
        self._last_llm_choice = self._select_value("#setup-ai-choice")
        self._last_speech_choice = self._select_value("#setup-speech-choice")
        self._sync_setup_controls()
        self._remember_current_form()
        self._request_runtime_readiness()

    def on_screen_resume(self) -> None:
        """Refresh externally saved setup only when the active form is clean."""
        if not self.is_mounted:
            return
        if self._current_form_dirty():
            self.set_status("Unsaved setup edits remain; save or discard before reloading.")
            return
        self._load_existing_setup()
        self._last_llm_choice = self._select_value("#setup-ai-choice")
        self._last_speech_choice = self._select_value("#setup-speech-choice")
        self._sync_text()
        self._sync_setup_controls()
        self._remember_current_form()
        self._request_runtime_readiness()

    def action_continue(self) -> bool:
        step = self.context.state.current_step
        # A pending role edit must reach the shared Save/Discard/Cancel guard
        # before the synthetic-test prerequisite is checked. Otherwise Continue
        # silently rejects the request and leaves unsaved fields unprotected.
        # After explicit save/discard, the pending transition re-enters this
        # method and checks the prerequisite against the durable form.
        if (
            step == "model-test"
            and not self.busy
            and not self._exit_confirmation_pending
            and not self._current_form_dirty()
        ):
            identity = self._current_llm_identity()
            if identity is None or self._model_test_identity != identity:
                self.set_status("Run the synthetic model test successfully before continuing.")
                return False
        if not super().action_continue():
            return False
        self._sync_setup_controls()
        if self.context.state.current_step not in self._preset_baseline_steps:
            self._remember_current_form()
        return True

    def action_back(self) -> bool:
        if not super().action_back():
            return False
        self._sync_setup_controls()
        self._schedule_form_baseline()
        return True

    def on_select_changed(self, event: Select.Changed) -> None:
        # Base-class handlers are dispatched by Textual itself (no super() call).
        if event.select.id == "setup-ai-choice":
            # Ignore queued initial/programmatic events; only a real change to
            # the current selection should replace the provider preset fields.
            choice = self._select_value("#setup-ai-choice")
            if (
                choice is not None
                and isinstance(event.value, str)
                and choice == event.value
                and choice != self._last_llm_choice
            ):
                self._last_llm_choice = choice
                self._capture_preset_baseline("provider-config")
                self._apply_llm_choice_defaults(force=True)
        elif event.select.id == "setup-model-picker" and isinstance(event.value, str):
            if event.value:
                self.query_one("#setup-provider-model", Input).value = event.value
        elif event.select.id == "setup-speech-choice":
            choice = self._select_value("#setup-speech-choice")
            if (
                choice is not None
                and isinstance(event.value, str)
                and choice == event.value
                and choice != self._last_speech_choice
            ):
                if self.context.state.current_step == "speech":
                    baseline = dict(self._form_baselines.get("speech", ()))
                    snapshot = dict(self._editable_snapshot())
                    dirty_fields = any(
                        value != baseline.get(key)
                        for key, value in snapshot.items()
                        if key != "setup-speech-choice"
                    )
                    if self._exit_confirmation_pending or (
                        "speech" in self._form_baselines and dirty_fields
                    ):
                        previous = self._last_speech_choice
                        if previous is not None:
                            self._assign_select(
                                self.query_one("#setup-speech-choice", Select), previous
                            )
                        if not self._exit_confirmation_pending:
                            self._request_dirty_transition(
                                Transition(TransitionKind.SPEECH_CHOICE, choice)
                            )
                        return
                self._last_speech_choice = choice
                self._apply_speech_choice_defaults(force=True)

    def _execute_custom_transition(self, transition: Transition) -> None:
        if transition.kind is TransitionKind.RECOMMENDED_ROLES:
            self.action_recommended_roles()
            return
        if transition.kind is TransitionKind.DISCOVER_VOICES:
            self.action_discover_voices()
            return
        if transition.kind is TransitionKind.DISCOVER_MODELS:
            self.action_discover_models()
            return
        if transition.kind is TransitionKind.SPEECH_CHOICE:
            choice = transition.argument or ""
            picker = self.query_one("#setup-speech-choice", Select)
            with picker.prevent(Select.Changed):
                picker.value = choice
            self._last_speech_choice = choice
            self._apply_speech_choice_defaults(force=True)
            self._sync_setup_controls()
            return
        super()._execute_custom_transition(transition)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"setup-provider-adapter", "setup-speech-adapter"}:
            self._sync_setup_controls()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name
        handlers = {
            "retry-readiness": self.action_retry_readiness,
            "discover-models": self.action_discover_models,
            "save-provider": self.action_save_provider,
            "test-provider": self.action_test_provider,
            "run-model-test": self.action_run_model_test,
            "recommended-roles": self.action_recommended_roles,
            "save-roles": self.action_save_roles,
            "save-speech": self.action_save_speech,
            "discover-voices": self.action_discover_voices,
            "preview-voice": self.action_preview_voice,
            "save-defaults": self.action_save_defaults,
            "ready-new": self.action_ready_new,
            "ready-home": self.action_ready_home,
        }
        handler = handlers.get(action or "")
        if handler is not None:
            event.stop()
            handler()
            return
        # Textual dispatches the base-class handlers itself; no super() call.

    def action_save_provider(self) -> bool:
        adapter = self._selected_llm_adapter()
        raw_name = self.query_one("#setup-provider-name", Input).value
        raw_model = self.query_one("#setup-provider-model", Input).value
        raw_values = (raw_name, raw_model) + tuple(
            self.query_one(selector, Input).value
            for selector in (
                "#setup-provider-adapter",
                "#setup-provider-base-url",
                "#setup-provider-credential-env",
                "#setup-provider-network",
            )
        )
        # Reject controls before trimming any optional value; the production
        # config validator must not be bypassed by first-run normalization.
        if any(
            ord(character) < 32 or ord(character) == 127
            for value in raw_values
            for character in value
        ):
            self.set_status("Provider settings must contain only single-line identifiers.")
            return False
        choice = self._select_value("#setup-ai-choice")
        typed_adapter = self.query_one("#setup-provider-adapter", Input).value.strip().lower()
        if choice != "manual" and typed_adapter and typed_adapter.replace("_", "-") != adapter:
            self.set_status(
                "The AI provider choice and the adapter field disagree; go back to the AI "
                "provider step or edit the adapter before saving."
            )
            return False
        name = raw_name.strip()
        model = raw_model.strip()
        if not name or not adapter or not model:
            self.set_status("Provider name, concrete adapter, and model are required.")
            return False
        controller = self.context.composition.provider_controller
        if controller.capability(adapter) != "llm":
            self.set_status("The selected adapter is not a language-model provider.")
            return False
        try:
            controller.save_provider(
                name,
                adapter,
                base_url=self._optional_input("#setup-provider-base-url"),
                default_model=model,
                credential_env=self._optional_input("#setup-provider-credential-env"),
                network_scope=self._optional_input("#setup-provider-network"),
            )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Provider save failed.", exc)
            return False
        self._llm_provider_name = name
        self._model_test_identity = None
        self._sync_text()
        self._remember_current_form()
        self.set_status(f"Saved provider {name}. Test the production connection to continue.")
        self._request_runtime_readiness()
        return True

    def action_test_provider(self) -> None:
        name = self._selected_llm_name()
        if name is None:
            self.set_status("Save or select a language-model provider first.")
            return
        try:
            health = self.context.composition.provider_controller.health(name)
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Connection failed.", exc)
            return
        message = str(redact(getattr(health, "message", "")))
        if not getattr(health, "healthy", False):
            self.set_status(f"{name} is not healthy: {message or 'provider reported unavailable'}")
            return
        self._sync_text()
        self.set_status(f"{name} connection is healthy. {message}".strip())

    def action_discover_models(self) -> None:
        if self.busy or self._exit_confirmation_pending:
            return
        if self.context.state.current_step == "provider-config" and self._current_form_dirty():
            # Option replacement must not overwrite unsaved model/provider edits.
            self._request_dirty_transition(Transition(TransitionKind.DISCOVER_MODELS))
            return
        name = self._selected_llm_name()
        if name is None:
            self.set_status("Save or select a language-model provider first.")
            return
        try:
            models = self.context.composition.provider_controller.llm(name).models()
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Model discovery failed.", exc)
            return
        current = self.query_one("#setup-provider-model", Input).value.strip()
        available = {model.model for model in models}
        self._model_options = tuple((model.model, model.model) for model in models)
        picker = self.query_one("#setup-model-picker", Select)
        picker.set_options(self._model_options)
        if current in available:
            # Model identity, not provider-discovery ordering, determines the selection.
            picker.value = current
            configured = self.context.composition.provider_controller.config().providers.get(name)
            if configured is not None and configured.default_model == current:
                self._remember_current_form()
        elif current:
            # A vanished configured model must not silently become another model.
            picker.value = Select.BLANK
            self.set_status(
                "Configured model is no longer available. Choose a replacement and save."
            )
            return
        elif models:
            picker.value = models[0].model
            self.query_one("#setup-provider-model", Input).value = models[0].model
        else:
            self.set_status("No models discovered. Check the provider connection and retry.")
            return
        self.set_status(f"Discovered {len(models)} model(s) from {name}.")

    def action_run_model_test(self) -> None:
        identity = self._current_llm_identity()
        name = self._selected_llm_name()
        if identity is None or name is None:
            self.set_status("Save a provider and model before running the model test.")
            return
        model = identity.split(":", 1)[1]
        self.set_busy(True, "Running synthetic language-model test…")
        started = monotonic()
        try:
            provider = self.context.composition.provider_controller.llm(name)
            health = provider.health()
            if not health.healthy:
                raise RuntimeError(health.message or "provider health check failed")
            response = provider.generate(
                LLMRequest(
                    messages=(
                        LLMMessage(
                            "user",
                            "Synthetic setup test. Reply briefly with the word READY.",
                        ),
                    ),
                    model=model,
                    max_output_tokens=32,
                )
            )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self._model_test_identity = None
            self._model_test_summary = "Model test failed. Press F1 for details."
            self.set_busy(False)
            self._sync_text()
            self.set_error("Model test failed.", exc)
            return
        elapsed = monotonic() - started
        preview = str(redact(response.text.replace("\n", " ")[:120]))
        self._model_test_identity = identity
        self._model_test_summary = (
            f"Model test succeeded in {elapsed:.2f}s. Response preview: {preview}"
        )
        self.set_busy(False)
        self._sync_text()
        self.set_status(self._model_test_summary)

    def action_recommended_roles(self) -> None:
        if self.busy or self._exit_confirmation_pending:
            return
        if self._current_form_dirty():
            # The preset overwrites editable role fields; require an explicit
            # Save/Discard/Cancel decision before replacing unsaved values.
            self._request_dirty_transition(Transition(TransitionKind.RECOMMENDED_ROLES))
            return
        identity = self._current_llm_identity()
        if identity is None:
            self.set_status("Choose and save a language model first.")
            return
        self._persist_roles({role: identity for role in _REQUIRED_SETUP_ROLES})

    def action_save_roles(self) -> bool:
        raw_values = {
            ModelRole.EPISODE_PLANNING: self.query_one("#setup-role-episode-planning", Input).value,
            ModelRole.HOST_GENERATION: self.query_one("#setup-role-host-generation", Input).value,
            ModelRole.DIRECTING: self.query_one("#setup-role-directing", Input).value,
            ModelRole.VERIFICATION: self.query_one("#setup-role-verification", Input).value,
        }
        if any(
            ord(character) < 32 or ord(character) == 127
            for value in raw_values.values()
            for character in value
        ):
            self.set_status("Role assignments must be single-line identifiers.")
            return False
        values = {role: value.strip() for role, value in raw_values.items()}
        if any(not value for value in values.values()):
            self.set_status("All required model roles need provider:model assignments.")
            return False
        return self._persist_roles(values)

    def _persist_roles(self, assignments: dict[ModelRole, str]) -> bool:
        try:
            self.settings.set_defaults(
                {role.value: identity for role, identity in assignments.items()}
            )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Role assignment failed.", exc)
            return False
        for role, identity in assignments.items():
            selector = {
                ModelRole.EPISODE_PLANNING: "#setup-role-episode-planning",
                ModelRole.HOST_GENERATION: "#setup-role-host-generation",
                ModelRole.DIRECTING: "#setup-role-directing",
                ModelRole.VERIFICATION: "#setup-role-verification",
            }[role]
            self.query_one(selector, Input).value = identity
        self._sync_text()
        self._remember_current_form()
        self.set_status("Saved recommended production model-role assignments.")
        self._request_runtime_readiness()
        return True

    def action_ready_new(self) -> None:
        self._clear_completed_setup_draft()
        cast(_NavigationApp, self.app).action_navigate("new")

    def action_ready_home(self) -> None:
        self._clear_completed_setup_draft()
        cast(_NavigationApp, self.app).action_navigate("home")
