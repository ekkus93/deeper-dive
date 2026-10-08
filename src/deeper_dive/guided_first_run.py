"""Production-backed first-run setup workflow."""

from __future__ import annotations

from time import monotonic
from typing import Protocol, cast

from textual.widget import Widget
from textual.widgets import Button, Input, Select

from deeper_dive.diagnostics import redact, sanitize_exception_message
from deeper_dive.first_run import FirstRunController
from deeper_dive.guided_workflow import CompletionProbe, WizardContext
from deeper_dive.llm import LLMMessage, LLMRequest
from deeper_dive.model_roles import ModelRole
from deeper_dive.settings_screen import SettingsController
from deeper_dive.wizard_shell import FirstRunWizardShell

_REQUIRED_SETUP_ROLES = (
    ModelRole.EPISODE_PLANNING,
    ModelRole.HOST_GENERATION,
    ModelRole.DIRECTING,
    ModelRole.VERIFICATION,
)


class _NavigationApp(Protocol):
    def action_navigate(self, destination: str) -> None: ...


class GuidedFirstRunWizard(FirstRunWizardShell):
    """Complete first-run flow routed through durable provider/settings boundaries."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe)
        self._llm_provider_name: str | None = None
        self._tts_provider_name: str | None = None
        self._model_test_identity: str | None = None
        self._model_test_summary = "Run a synthetic model test before continuing."
        self._model_options: tuple[tuple[str, str], ...] = ()
        self._voice_options: tuple[tuple[str, str], ...] = ()

    @property
    def settings(self) -> SettingsController:
        return SettingsController(self.context.composition.provider_controller)

    def step_controls(self) -> tuple[Widget, ...]:
        return (
            *super().step_controls(),
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
        if step_key in {"welcome", "system-check"}:
            return super().step_content(step_key)
        if step_key == "ai-provider":
            check = FirstRunController(self.context.composition.provider_controller).system_check()
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
            from deeper_dive.guided_readiness import first_run_readiness

            ready = first_run_readiness(self.context)
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
        self._sync_setup_controls()

    def action_continue(self) -> None:
        step = self.context.state.current_step
        if step == "model-test":
            identity = self._current_llm_identity()
            if identity is None or self._model_test_identity != identity:
                self.set_status("Run the synthetic model test successfully before continuing.")
                return
        super().action_continue()
        self._sync_setup_controls()

    def action_back(self) -> None:
        super().action_back()
        self._sync_setup_controls()

    def on_select_changed(self, event: Select.Changed) -> None:
        super().on_select_changed(event)
        if event.select.id == "setup-ai-choice":
            self._apply_llm_choice_defaults(force=True)
        elif event.select.id == "setup-model-picker" and isinstance(event.value, str):
            if event.value:
                self.query_one("#setup-provider-model", Input).value = event.value
        elif event.select.id == "setup-speech-choice":
            self._apply_speech_choice_defaults(force=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name
        handlers = {
            "discover-models": self.action_discover_models,
            "save-provider": self.action_save_provider,
            "test-provider": self.action_test_provider,
            "run-model-test": self.action_run_model_test,
            "recommended-roles": self.action_recommended_roles,
            "save-roles": self.action_save_roles,
            "save-speech": self.action_save_speech,
            "discover-voices": self.action_discover_voices,
            "save-defaults": self.action_save_defaults,
            "ready-new": self.action_ready_new,
            "ready-home": self.action_ready_home,
        }
        handler = handlers.get(action or "")
        if handler is not None:
            event.stop()
            handler()
            return
        super().on_button_pressed(event)

    def action_save_provider(self) -> None:
        adapter = self._selected_llm_adapter()
        name = self.query_one("#setup-provider-name", Input).value.strip()
        model = self.query_one("#setup-provider-model", Input).value.strip()
        if not name or not adapter or not model:
            self.set_status("Provider name, concrete adapter, and model are required.")
            return
        controller = self.context.composition.provider_controller
        if controller.capability(adapter) != "llm":
            self.set_status("The selected adapter is not a language-model provider.")
            return
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
            self.set_status(f"Provider save failed: {sanitize_exception_message(exc)}")
            return
        self._llm_provider_name = name
        self._model_test_identity = None
        self._sync_text()
        self.set_status(f"Saved provider {name}. Test the production connection to continue.")

    def action_test_provider(self) -> None:
        name = self._selected_llm_name()
        if name is None:
            self.set_status("Save or select a language-model provider first.")
            return
        try:
            health = self.context.composition.provider_controller.health(name)
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_status(f"Connection failed: {sanitize_exception_message(exc)}")
            return
        message = str(redact(getattr(health, "message", "")))
        if not getattr(health, "healthy", False):
            self.set_status(f"{name} is not healthy: {message or 'provider reported unavailable'}")
            return
        self._sync_text()
        self.set_status(f"{name} connection is healthy. {message}".strip())

    def action_discover_models(self) -> None:
        name = self._selected_llm_name()
        if name is None:
            self.set_status("Save or select a language-model provider first.")
            return
        try:
            models = self.context.composition.provider_controller.llm(name).models()
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_status(f"Model discovery failed: {sanitize_exception_message(exc)}")
            return
        self._model_options = tuple((model.model, model.model) for model in models)
        picker = self.query_one("#setup-model-picker", Select)
        picker.set_options(self._model_options)
        if models:
            picker.value = models[0].model
            self.query_one("#setup-provider-model", Input).value = models[0].model
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
            self._model_test_summary = "Model test failed: " + sanitize_exception_message(exc)
            self.set_busy(False)
            self._sync_text()
            self.set_status(self._model_test_summary)
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
        identity = self._current_llm_identity()
        if identity is None:
            self.set_status("Choose and save a language model first.")
            return
        self._persist_roles({role: identity for role in _REQUIRED_SETUP_ROLES})

    def action_save_roles(self) -> None:
        values = {
            ModelRole.EPISODE_PLANNING: self.query_one(
                "#setup-role-episode-planning", Input
            ).value.strip(),
            ModelRole.HOST_GENERATION: self.query_one(
                "#setup-role-host-generation", Input
            ).value.strip(),
            ModelRole.DIRECTING: self.query_one("#setup-role-directing", Input).value.strip(),
            ModelRole.VERIFICATION: self.query_one("#setup-role-verification", Input).value.strip(),
        }
        if any(not value for value in values.values()):
            self.set_status("All required model roles need provider:model assignments.")
            return
        self._persist_roles(values)

    def _persist_roles(self, assignments: dict[ModelRole, str]) -> None:
        try:
            for role, identity in assignments.items():
                self.settings.save_model_default(role.value, identity)
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_status(f"Role assignment failed: {sanitize_exception_message(exc)}")
            return
        for role, identity in assignments.items():
            selector = {
                ModelRole.EPISODE_PLANNING: "#setup-role-episode-planning",
                ModelRole.HOST_GENERATION: "#setup-role-host-generation",
                ModelRole.DIRECTING: "#setup-role-directing",
                ModelRole.VERIFICATION: "#setup-role-verification",
            }[role]
            self.query_one(selector, Input).value = identity
        self._sync_text()
        self.set_status("Saved recommended production model-role assignments.")

    def action_save_speech(self) -> None:
        choice = self._select_value("#setup-speech-choice") or "kitten"
        if choice == "deferred":
            self.settings.set_default("speech_setup", "deferred")
            self.settings.set_default("tts_provider", "")
            self.settings.set_default("tts_voice", "")
            self._tts_provider_name = None
            self._sync_text()
            self.set_status("Speech intentionally deferred. Audio generation will remain blocked.")
            return

        adapter = (
            self.query_one("#setup-speech-adapter", Input).value.strip()
            if choice == "advanced"
            else choice
        )
        name = self.query_one("#setup-speech-name", Input).value.strip() or "speech"
        controller = self.context.composition.provider_controller
        if controller.capability(adapter) != "tts":
            self.set_status("Choose a concrete speech/TTS adapter.")
            return
        voices = tuple(
            item.strip()
            for item in self.query_one("#setup-speech-voices", Input).value.split(",")
            if item.strip()
        )
        try:
            controller.save_provider(
                name,
                adapter,
                base_url=self._optional_input("#setup-speech-base-url"),
                default_model=self._optional_input("#setup-speech-model"),
                credential_env=self._optional_input("#setup-speech-credential-env"),
                network_scope=self._optional_input("#setup-speech-network"),
                voices=voices,
            )
            self.settings.set_default("speech_setup", "configured")
            self.settings.set_default("tts_provider", name)
            self.settings.set_default("tts_voice", "")
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_status(f"Speech configuration failed: {sanitize_exception_message(exc)}")
            return
        self._tts_provider_name = name
        self._sync_text()
        self.set_status(f"Saved speech provider {name}. Discover and choose voices next.")

    def action_discover_voices(self) -> None:
        name = self._selected_tts_name()
        if name is None:
            self.set_status("Configure a speech provider before discovering voices.")
            return
        try:
            voices = self.context.composition.provider_controller.tts(name).voices()
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_status(f"Voice discovery failed: {sanitize_exception_message(exc)}")
            return
        self._voice_options = tuple((voice.name, voice.id) for voice in voices)
        for selector in ("#setup-host1-voice", "#setup-host2-voice"):
            widget = self.query_one(selector, Select)
            widget.set_options(self._voice_options)
        if voices:
            self.query_one("#setup-host1-voice", Select).value = voices[0].id
            self.query_one("#setup-host2-voice", Select).value = (
                voices[1].id if len(voices) > 1 else voices[0].id
            )
        self.set_status(f"Discovered {len(voices)} friendly voice option(s) from {name}.")

    def action_save_defaults(self) -> None:
        config = self.context.composition.provider_controller.config()
        deferred = config.defaults.get("speech_setup") == "deferred"
        voice1 = self._select_value("#setup-host1-voice")
        voice2 = self._select_value("#setup-host2-voice")
        if not deferred and (not voice1 or not voice2):
            self.set_status("Choose Host 1 and Host 2 voices before continuing.")
            return
        duration = self._select_value("#setup-duration")
        research = self._select_value("#setup-research-default")
        if not duration or not research:
            self.set_status("Choose default duration and research level.")
            return
        try:
            self.settings.set_default("quick_deep_dive_duration_minutes", duration)
            self.settings.set_default("research_policy", research)
            if not deferred:
                provider = self._selected_tts_name()
                if provider is None:
                    raise ValueError("speech provider is not configured")
                self.settings.save_tts_defaults(provider, voice1 or "")
                self.settings.set_default("tts_voice_host_1", voice1 or "")
                self.settings.set_default("tts_voice_host_2", voice2 or "")
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_status(f"Default save failed: {sanitize_exception_message(exc)}")
            return
        self._sync_text()
        self.set_status("Saved voice, duration, and research defaults.")

    def action_ready_new(self) -> None:
        cast(_NavigationApp, self.app).action_navigate("new")

    def action_ready_home(self) -> None:
        cast(_NavigationApp, self.app).action_navigate("home")

    def _load_existing_setup(self) -> None:
        controller = self.context.composition.provider_controller
        config = controller.config()
        llm_names = [
            name
            for name, provider in sorted(config.providers.items())
            if controller.capability(provider.provider_type) == "llm"
        ]
        if llm_names:
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
            self.query_one("#setup-ai-choice", Select).value = choice

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
            self.query_one("#setup-speech-choice", Select).value = speech_choice
        elif config.defaults.get("speech_setup") == "deferred":
            self.query_one("#setup-speech-choice", Select).value = "deferred"

        defaults = config.defaults
        duration = defaults.get("quick_deep_dive_duration_minutes", "20")
        if duration in {"10", "20", "30"}:
            self.query_one("#setup-duration", Select).value = duration
        research = defaults.get("research_policy", "useful")
        if research in {"off", "useful", "aggressive"}:
            self.query_one("#setup-research-default", Select).value = research
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
                "#setup-duration",
                "#setup-research-default",
                "#setup-save-defaults",
            },
            "ready": {"#setup-ready-new", "#setup-ready-home"},
        }
        all_ids = set().union(*visible_ids.values())
        shown = visible_ids.get(step, set())
        for selector in all_ids:
            self.query_one(selector).display = selector in shown

        if step == "provider-config":
            self._apply_llm_choice_defaults(force=False)
            manual = self._select_value("#setup-ai-choice") == "manual"
            self.query_one("#setup-provider-adapter", Input).display = manual
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
            self._apply_speech_choice_defaults(force=False)
            choice = self._select_value("#setup-speech-choice")
            custom = choice == "advanced"
            deferred = choice == "deferred"
            self.query_one("#setup-speech-adapter", Input).display = custom
            for selector in (
                "#setup-speech-name",
                "#setup-speech-base-url",
                "#setup-speech-model",
                "#setup-speech-credential-env",
                "#setup-speech-network",
                "#setup-speech-voices",
            ):
                self.query_one(selector).display = not deferred

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
        value = self.query_one(selector, Input).value.strip()
        return value or None

    def _select_value(self, selector: str) -> str | None:
        value = self.query_one(selector, Select).value
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _choice_for_adapter(adapter: str, base_url: str | None) -> str:
        normalized = adapter.strip().lower().replace("_", "-")
        if normalized == "openai" and base_url and "api.openai.com" not in base_url:
            return "openai-compatible"
        if normalized in {"ollama", "llama-server", "openai"}:
            return normalized
        return "manual"
