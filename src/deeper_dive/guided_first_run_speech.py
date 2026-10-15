"""Speech and voice-default actions for the first-run wizard."""

from __future__ import annotations

from textual.widgets import Input, Select

from deeper_dive.guided_first_run_form import FirstRunFormControls
from deeper_dive.voice_preview import VoicePreviewService
from deeper_dive.wizard_transitions import Transition, TransitionKind


class FirstRunSpeechActions(FirstRunFormControls):
    """Speech and voice-default actions for the first-run wizard."""

    def action_save_speech(self) -> bool:
        choice = self._select_value("#setup-speech-choice") or "kitten"
        if choice == "deferred":
            try:
                self.settings.set_defaults(
                    {"speech_setup": "deferred", "tts_provider": "", "tts_voice": ""}
                )
            except (KeyError, OSError, RuntimeError, ValueError) as exc:
                # Deferred speech uses the same loss-safe, sanitized save
                # contract as configured speech providers and other steps.
                self.set_error("Speech configuration failed.", exc)
                return False
            self._tts_provider_name = None
            self._sync_text()
            self._remember_current_form()
            self.set_status("Speech intentionally deferred. Audio generation will remain blocked.")
            self._request_runtime_readiness()
            return True

        raw_speech = tuple(
            self.query_one(selector, Input).value
            for selector in (
                "#setup-speech-name",
                "#setup-speech-adapter",
                "#setup-speech-base-url",
                "#setup-speech-model",
                "#setup-speech-credential-env",
                "#setup-speech-network",
                "#setup-speech-voices",
            )
        )
        if any(
            ord(character) < 32 or ord(character) == 127
            for value in raw_speech
            for character in value
        ):
            self.set_status("Speech provider and voice fields must be single-line.")
            return False
        adapter = (
            self.query_one("#setup-speech-adapter", Input).value.strip()
            if choice == "advanced"
            else choice
        )
        name = self.query_one("#setup-speech-name", Input).value.strip() or "speech"
        controller = self.context.composition.provider_controller
        if controller.capability(adapter) != "tts":
            self.set_status("Choose a concrete speech/TTS adapter.")
            return False
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
                default_updates={
                    "speech_setup": "configured",
                    "tts_provider": name,
                    "tts_voice": "",
                },
            )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Speech configuration failed.", exc)
            return False
        self._tts_provider_name = name
        self._sync_text()
        self._remember_current_form()
        self.set_status(f"Saved speech provider {name}. Discover and choose voices next.")
        self._request_runtime_readiness()
        return True

    def action_discover_voices(self) -> None:
        if self.busy or self._exit_confirmation_pending:
            return
        if self.context.state.current_step == "voice-defaults" and self._current_form_dirty():
            # A discovery refresh replaces Select options. The user must decide
            # what happens to unsaved voice/duration/research defaults first.
            self._request_dirty_transition(Transition(TransitionKind.DISCOVER_VOICES))
            return
        name = self._selected_tts_name()
        if name is None:
            self.set_status("Configure a speech provider before discovering voices.")
            return
        try:
            voices = self.context.composition.provider_controller.tts(name).voices()
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Voice discovery failed.", exc)
            return

        selectors = ("#setup-host1-voice", "#setup-host2-voice")
        previous = tuple(self._select_value(selector) for selector in selectors)
        config = self.context.composition.provider_controller.config()
        defaults = config.defaults
        saved = (
            (
                defaults.get("tts_voice_host_1") or defaults.get("tts_voice"),
                defaults.get("tts_voice_host_2") or defaults.get("tts_voice"),
            )
            if defaults.get("tts_provider") == name
            else (None, None)
        )
        self._voice_options = tuple((voice.name, voice.id) for voice in voices)
        available = {voice.id for voice in voices}
        vanished = []
        for index, selector in enumerate(selectors):
            widget = self.query_one(selector, Select)
            widget.set_options(self._voice_options)
            selected = previous[index] or saved[index]
            if selected in available:
                # Discovery order may change: retain stable saved voice IDs.
                widget.value = selected
            elif selected:
                # A removed voice must not silently become another voice.
                widget.value = Select.BLANK
                vanished.append(f"Host {index + 1}")
            elif voices:
                widget.value = voices[min(index, len(voices) - 1)].id
        if not vanished and all(
            selected and self._select_value(selector) == selected
            for selector, selected in zip(selectors, saved, strict=True)
        ):
            # Rediscovered selections matching durable defaults are hydration,
            # not new unsaved user edits. The dirty guard above excluded edits.
            self._remember_current_form()
        if vanished:
            self.set_status(
                "Voice selection no longer available for "
                + ", ".join(vanished)
                + ". Choose replacement voice(s) and save defaults."
            )
        else:
            self.set_status(f"Discovered {len(voices)} friendly voice option(s) from {name}.")

    def action_preview_voice(self) -> None:
        name = self._selected_tts_name()
        voice = self._select_value("#setup-host1-voice")
        if name is None or not voice:
            self.set_status("Configure speech and choose a Host 1 voice before previewing.")
            return
        try:
            provider = self.context.composition.provider_controller.tts(name)
            path = VoicePreviewService(
                self.context.composition.service.workspaces.data_dir / "voice-previews"
            ).preview(provider, voice=voice)
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Voice preview failed.", exc)
            return
        self.set_status(f"Voice preview synthesized through {name}: {path.name}")

    def action_save_defaults(self) -> bool:
        config = self.context.composition.provider_controller.config()
        deferred = config.defaults.get("speech_setup") == "deferred"
        voice1 = self._select_value("#setup-host1-voice")
        voice2 = self._select_value("#setup-host2-voice")
        if not deferred and (not voice1 or not voice2):
            self.set_status("Choose Host 1 and Host 2 voices before continuing.")
            return False
        duration = self._select_value("#setup-duration")
        research = self._select_value("#setup-research-default")
        if not duration or not research:
            self.set_status("Choose default duration and research level.")
            return False
        try:
            candidate = {
                "quick_deep_dive_duration_minutes": duration,
                "research_policy": research,
            }
            if not deferred:
                provider = self._selected_tts_name()
                if provider is None:
                    raise ValueError("speech provider is not configured")
                candidate.update(
                    {
                        "tts_provider": provider,
                        "tts_voice": voice1 or "",
                        "tts_voice_host_1": voice1 or "",
                        "tts_voice_host_2": voice2 or "",
                    }
                )
            self.settings.set_defaults(candidate)
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Default save failed.", exc)
            return False
        self._sync_text()
        self._remember_current_form()
        self.set_status("Saved voice, duration, and research defaults.")
        self._request_runtime_readiness()
        return True
