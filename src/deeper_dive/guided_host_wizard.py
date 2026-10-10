"""Friendly host selection for the guided New Deep Dive workflow."""

from __future__ import annotations

from dataclasses import replace

from textual.widget import Widget
from textual.widgets import Button, Input, Select, Static

from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_source_wizard import GuidedSourceWizard
from deeper_dive.guided_workflow import CompletionProbe, WizardContext
from deeper_dive.hosts import HostProfile, create_host_from_preset, preset_names
from deeper_dive.storage.episode_repositories import HostProfileRecord
from deeper_dive.voice_preview import VoicePreviewService


class GuidedHostWizard(GuidedSourceWizard):
    """Select and order friendly host profiles without exposing raw IDs."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe)
        self._selected_host_ids: list[str] = []

    def _editable_snapshot(self) -> tuple[tuple[str, str], ...]:
        values = list(super()._editable_snapshot())
        if self.context.state.current_step == "hosts":
            values.append(
                (
                    "__episode_host_order__",
                    f"{self.context.episode_id or ''}:{','.join(self._selected_host_ids)}",
                )
            )
        return tuple(values)

    def step_controls(self) -> tuple[Widget, ...]:
        return (
            *super().step_controls(),
            Button(
                "Create Recommended Pair",
                id="guided-host-recommended",
                name="recommended-hosts",
            ),
            Select(
                [(name.replace("_", " ").title(), name) for name in preset_names()],
                value="curious_explainer",
                allow_blank=False,
                id="guided-host-preset",
            ),
            Input(placeholder="Host display name", id="guided-host-name"),
            Input(placeholder="Host role", id="guided-host-role"),
            Input(placeholder="Host expertise", id="guided-host-expertise"),
            Input(placeholder="Host instructions", id="guided-host-instructions"),
            Button("Create Host", id="guided-host-create", name="create-host"),
            Button("Save Host", id="guided-host-save", name="save-host"),
            Select([], allow_blank=True, id="guided-host-picker"),
            Static("", id="guided-host-details"),
            Button(
                "Add to Episode",
                id="guided-host-select",
                name="select-host",
            ),
            Static("", id="guided-host-order"),
            Button("Move Up", id="guided-host-up", name="host-up"),
            Button("Move Down", id="guided-host-down", name="host-down"),
            Button(
                "Remove from Episode",
                id="guided-host-remove",
                name="remove-selected-host",
            ),
            Button(
                "Preview Voice",
                id="guided-host-preview",
                name="preview-host-voice",
            ),
            Button(
                "Save Host Order",
                id="guided-host-order-save",
                name="save-host-order",
            ),
        )

    def step_content(self, step_key: str) -> str:
        if step_key == "hosts":
            return (
                "Choose one or more conversation hosts. The normal path shows friendly "
                "names, roles, and voice names; internal host IDs stay hidden. "
                "Voice Preview may contact a remote TTS provider if cloud speech is "
                "configured. Order is persisted into the production episode configuration."
            )
        return super().step_content(step_key)

    def on_mount(self) -> None:
        super().on_mount()
        self._load_episode_host_order()
        self._refresh_hosts()
        self._toggle()
        self._schedule_form_baseline()

    def action_continue(self) -> bool:
        if not super().action_continue():
            return False
        self._refresh_hosts()
        self._toggle()
        self._schedule_form_baseline()
        return True

    def action_back(self) -> bool:
        if not super().action_back():
            return False
        self._refresh_hosts()
        self._toggle()
        self._schedule_form_baseline()
        return True

    def on_select_changed(self, event: Select.Changed) -> None:
        super().on_select_changed(event)
        if event.select.id == "guided-host-picker":
            self._load_selected_host()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "recommended-hosts": self.action_create_recommended_hosts,
            "create-host": self.action_create_host,
            "save-host": self.action_save_host,
            "select-host": self.action_select_host,
            "host-up": lambda: self._move_selected_host(-1),
            "host-down": lambda: self._move_selected_host(1),
            "remove-selected-host": self.action_remove_selected_host,
            "preview-host-voice": self.action_preview_host_voice,
            "save-host-order": self.action_save_host_order,
        }
        handler = handlers.get(event.button.name or "")
        if handler is not None:
            event.stop()
            handler()
            return
        super().on_button_pressed(event)

    def action_create_recommended_hosts(self) -> None:
        project_id = self.context.project_id
        if project_id is None:
            self.set_status("Create the project before choosing hosts.")
            return
        repository = self.context.composition.service.hosts(project_id)
        existing = repository.list_hosts(project_id)
        created: list[str] = []
        for ordinal, preset in enumerate(("curious_explainer", "skeptic")):
            match = next((host for host in existing if host.preset_origin == preset), None)
            if match is not None:
                created.append(match.id)
                continue
            host = create_host_from_preset(preset, project_id)
            provider, voice = self._default_voice(ordinal)
            host.tts_provider = provider
            host.tts_voice = voice
            repository.create_host(host.to_record())
            created.append(host.id)
        for host_id in created:
            if host_id not in self._selected_host_ids:
                self._selected_host_ids.append(host_id)
        self._refresh_hosts(created[0] if created else None)
        self.set_status("Created/selected the recommended Curious Explainer and Skeptic pair.")

    def action_create_host(self) -> None:
        project_id = self.context.project_id
        if project_id is None:
            self.set_status("Create the project before creating a host.")
            return
        preset_value = self.query_one("#guided-host-preset", Select).value
        preset = str(preset_value)
        if preset not in preset_names():
            self.set_status("Choose a valid host preset.")
            return
        try:
            host = create_host_from_preset(preset, project_id)
            self._apply_host_form(host)
            provider, voice = self._default_voice(len(self._selected_host_ids))
            if host.tts_provider is None:
                host.tts_provider = provider
            if host.tts_voice is None:
                host.tts_voice = voice
            self.context.composition.service.hosts(project_id).create_host(host.to_record())
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Host creation failed.", exc)
            return
        self._refresh_hosts(host.id)
        self._remember_current_form()
        self.set_status(f"Created host {host.display_name}.")

    def action_save_host(self) -> None:
        project_id = self.context.project_id
        record = self._selected_host_record()
        if project_id is None or record is None:
            self.set_status("Choose a host to edit.")
            return
        try:
            host = HostProfile.from_record(record)
            self._apply_host_form(host, clear_optional=True)
            self.context.composition.service.hosts(project_id).update_host(host.to_record())
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Host save failed.", exc)
            return
        self._refresh_hosts(record.id)
        self._remember_current_form()
        self.set_status(f"Saved host {host.display_name}.")

    def action_select_host(self) -> None:
        record = self._selected_host_record()
        if record is None:
            self.set_status("Choose a host to add.")
            return
        if record.id not in self._selected_host_ids:
            self._selected_host_ids.append(record.id)
        self._refresh_host_order()
        self.set_status(f"Selected {record.display_name} for this episode.")

    def action_remove_selected_host(self) -> None:
        record = self._selected_host_record()
        if record is None or record.id not in self._selected_host_ids:
            self.set_status("Choose a selected host to remove from the episode.")
            return
        self._selected_host_ids.remove(record.id)
        self._refresh_host_order()
        self.set_status(f"Removed {record.display_name} from this episode.")

    def action_preview_host_voice(self) -> None:
        record = self._selected_host_record()
        if record is None:
            self.set_status("Choose a host before previewing a voice.")
            return
        if not record.tts_provider or not record.tts_voice:
            self.set_status(f"{record.display_name} has no configured voice.")
            return
        try:
            provider = self.context.composition.provider_controller.tts(record.tts_provider)
            voice = next(
                (item for item in provider.voices() if item.id == record.tts_voice),
                None,
            )
            if voice is None:
                raise ValueError("The configured voice is no longer available.")
            path = VoicePreviewService(
                self.context.composition.service.workspaces.data_dir / "voice-previews"
            ).preview(provider, voice=voice.id)
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Voice preview failed.", exc)
            return
        self.set_status(f"Previewed {voice.name}: {path.name}")

    def action_save_host_order(self) -> None:
        project_id = self.context.project_id
        if project_id is None or not self._selected_host_ids:
            self.set_status("Select at least one host before continuing.")
            return
        service = EpisodeConfigurationService(
            self.context.composition.database_for_project(project_id)
        )
        try:
            if self.context.episode_id is None:
                project = self.context.composition.service.open_project(project_id)
                if project is None:
                    raise ValueError("Project is no longer available.")
                config = EpisodeConfiguration(
                    title=f"{project.name} Deep Dive",
                    focus=self._project_instruction("Main curiosity"),
                    audience=self._project_instruction("Audience") or "general",
                    target_duration_seconds=self._default_duration_seconds(),
                    host_ids=tuple(self._selected_host_ids),
                )
                episode = service.create(project_id, config)
                self.context.episode_id = episode.id
            else:
                current = service.load_configuration(self.context.episode_id)
                service.edit(
                    self.context.episode_id,
                    replace(current, host_ids=tuple(self._selected_host_ids)),
                )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Host order save failed.", exc)
            return
        self._sync_text()
        self._remember_current_form()
        self.set_status("Saved ordered episode hosts through EpisodeConfigurationService.")

    def _move_selected_host(self, delta: int) -> None:
        record = self._selected_host_record()
        if record is None or record.id not in self._selected_host_ids:
            self.set_status("Choose a selected episode host to reorder.")
            return
        index = self._selected_host_ids.index(record.id)
        target = max(0, min(len(self._selected_host_ids) - 1, index + delta))
        if target != index:
            self._selected_host_ids[index], self._selected_host_ids[target] = (
                self._selected_host_ids[target],
                self._selected_host_ids[index],
            )
        self._refresh_host_order()

    def _load_episode_host_order(self) -> None:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            return
        try:
            config = EpisodeConfigurationService(
                self.context.composition.database_for_project(project_id)
            ).load_configuration(episode_id)
        except (KeyError, ValueError):
            return
        self._selected_host_ids = list(config.host_ids)

    def _refresh_hosts(self, preferred_host_id: str | None = None) -> None:
        project_id = self.context.project_id
        picker = self.query_one("#guided-host-picker", Select)
        if project_id is None:
            picker.set_options([])
            self._refresh_host_order()
            return
        records = self.context.composition.service.hosts(project_id).list_hosts(project_id)
        picker.set_options(
            [
                (
                    f"{record.display_name} — {record.role or 'Host'} — "
                    f"{self._voice_label(record.tts_provider, record.tts_voice)}",
                    record.id,
                )
                for record in records
            ]
        )
        ids = {record.id for record in records}
        if preferred_host_id in ids:
            picker.value = preferred_host_id
        elif records and (not isinstance(picker.value, str) or picker.value not in ids):
            picker.value = records[0].id
        self._load_selected_host()
        self._refresh_host_order()

    def _load_selected_host(self) -> None:
        record = self._selected_host_record()
        details = self.query_one("#guided-host-details", Static)
        if record is None:
            details.update("No host selected.")
            return
        host = HostProfile.from_record(record)
        self.query_one("#guided-host-name", Input).value = host.display_name
        self.query_one("#guided-host-role", Input).value = host.role
        self.query_one("#guided-host-expertise", Input).value = host.expertise
        self.query_one("#guided-host-instructions", Input).value = host.instructions
        if host.preset_origin in preset_names():
            self.query_one("#guided-host-preset", Select).value = host.preset_origin
        details.update(
            "\n".join(
                (
                    f"Name: {host.display_name}",
                    f"Role: {host.role or 'Host'}",
                    f"Behavior: {self._behavior_summary(host)}",
                    f"Voice: {self._voice_label(host.tts_provider, host.tts_voice)}",
                    (
                        "Selected for episode: yes"
                        if host.id in self._selected_host_ids
                        else "Selected for episode: no"
                    ),
                )
            )
        )

    def _refresh_host_order(self) -> None:
        project_id = self.context.project_id
        output = self.query_one("#guided-host-order", Static)
        if project_id is None or not self._selected_host_ids:
            output.update("Episode hosts: none selected.")
            return
        repository = self.context.composition.service.hosts(project_id)
        rows: list[str] = []
        valid_ids: list[str] = []
        for host_id in self._selected_host_ids:
            record = repository.get_host(host_id)
            if record is None:
                continue
            valid_ids.append(host_id)
            rows.append(
                f"{len(rows) + 1}. {record.display_name} — {record.role or 'Host'} — "
                f"{self._voice_label(record.tts_provider, record.tts_voice)}"
            )
        self._selected_host_ids = valid_ids
        output.update("Episode host order:\n" + "\n".join(rows) if rows else "Episode hosts: none.")

    def _selected_host_record(self) -> HostProfileRecord | None:
        project_id = self.context.project_id
        value = self.query_one("#guided-host-picker", Select).value
        if project_id is None or not isinstance(value, str):
            return None
        return self.context.composition.service.hosts(project_id).get_host(value)

    def _apply_host_form(self, host: HostProfile, *, clear_optional: bool = False) -> None:
        name = self.query_one("#guided-host-name", Input).value.strip()
        if name:
            host.display_name = name
        role = self.query_one("#guided-host-role", Input).value.strip()
        if role or clear_optional:
            host.role = role
        host.expertise = self.query_one("#guided-host-expertise", Input).value.strip()
        instructions = self.query_one("#guided-host-instructions", Input).value.strip()
        if instructions or clear_optional:
            host.instructions = instructions
        host.validate()

    def _default_voice(self, ordinal: int) -> tuple[str | None, str | None]:
        defaults = self.context.composition.provider_controller.config().defaults
        provider = defaults.get("tts_provider", "").strip() or None
        voice_key = "tts_voice_host_1" if ordinal == 0 else "tts_voice_host_2"
        voice = defaults.get(voice_key, "").strip() or defaults.get("tts_voice", "").strip() or None
        return provider, voice

    def _voice_label(self, provider_id: str | None, voice_id: str | None) -> str:
        if not provider_id or not voice_id:
            return "No voice"
        try:
            provider = self.context.composition.provider_controller.tts(provider_id)
            voice = next((item for item in provider.voices() if item.id == voice_id), None)
        except (KeyError, RuntimeError, ValueError):
            voice = None
        return voice.name if voice is not None else "Unavailable voice"

    @staticmethod
    def _behavior_summary(host: HostProfile) -> str:
        if not host.behavior:
            return host.instructions or "Custom conversational behavior"
        parts = [
            f"{key.replace('_', ' ')} {float(value):.1f}"
            for key, value in sorted(host.behavior.items())
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        return ", ".join(parts[:3]) or host.instructions or "Custom conversational behavior"

    def _project_instruction(self, label: str) -> str:
        project_id = self.context.project_id
        if project_id is None:
            return ""
        project = self.context.composition.service.open_project(project_id)
        if project is None:
            return ""
        prefix = label + ":"
        for line in project.instructions.splitlines():
            if line.startswith(prefix):
                return line.removeprefix(prefix).strip()
        return ""

    def _default_duration_seconds(self) -> int:
        value = self.context.composition.provider_controller.config().defaults.get(
            "quick_deep_dive_duration_minutes",
            "20",
        )
        try:
            return max(60, int(value) * 60)
        except ValueError:
            return 1200

    def _toggle(self) -> None:
        super()._toggle()
        step = self.context.state.current_step
        for selector in (
            "#guided-host-recommended",
            "#guided-host-preset",
            "#guided-host-name",
            "#guided-host-role",
            "#guided-host-expertise",
            "#guided-host-instructions",
            "#guided-host-create",
            "#guided-host-save",
            "#guided-host-picker",
            "#guided-host-details",
            "#guided-host-select",
            "#guided-host-order",
            "#guided-host-up",
            "#guided-host-down",
            "#guided-host-remove",
            "#guided-host-preview",
            "#guided-host-order-save",
        ):
            self.query_one(selector).display = step == "hosts"
