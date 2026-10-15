"""Host list/order loading, form application and display helpers for the host wizard."""

from __future__ import annotations

import sqlite3

from textual.widgets import Input, Select, Static

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.guided_source_wizard import GuidedSourceWizard
from deeper_dive.guided_workflow import CompletionProbe, WizardContext
from deeper_dive.hosts import HostProfile, preset_names
from deeper_dive.storage.episode_repositories import HostProfileRecord


class HostWizardSupport(GuidedSourceWizard):
    """Host list/order loading, form application and display helpers for the host wizard."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe)
        self._selected_host_ids: list[str] = []
        # Last host-order load failure, republished after a status reset.
        self.host_order_notice = ""
        self._loaded_host_id: str | None = None
        self._loaded_host_record: HostProfileRecord | None = None
        # Form signature of the last successful Create Host: repeating the same
        # request (double Enter/click) must not create a second identical host.
        self._last_created_host_signature: tuple[str, str, str, str, object] | None = None
        # The created host the signature belongs to: loading any other host ends the
        # double-submit window, so a deliberate later identical Create is allowed.
        self._last_created_host_id: str | None = None

    def _load_episode_host_order(self) -> bool:
        """Load the saved order; ``False`` means the current in-memory order was kept."""

        # A notice describes the last load only; never republish an older failure.
        self.host_order_notice = ""
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            return False
        try:
            config = EpisodeConfigurationService(
                self.context.composition.database_for_project(project_id)
            ).load_configuration(episode_id)
        except (KeyError, OSError, ValueError, sqlite3.Error) as exc:
            # Keep the current in-memory order; never present a silent empty list.
            self.host_order_notice = (
                "Could not load the saved episode host order: "
                + sanitize_exception_message(exc)
                + " The current order was kept."
            )
            self.set_status(self.host_order_notice)
            return False
        self._selected_host_ids = list(config.host_ids)
        self.host_order_notice = ""
        return True

    def _refresh_hosts(
        self, preferred_host_id: str | None = None, *, preserve_dirty: bool = True
    ) -> None:
        project_id = self.context.project_id
        picker = self.query_one("#guided-host-picker", Select)
        # An unrelated refresh may update picker options, but it must not
        # rehydrate a durable host over unsaved edits or change their target.
        pending = (
            self._host_form_values()
            if preserve_dirty
            and self.context.state.current_step == "hosts"
            and self._loaded_host_id is not None
            and self._host_profile_dirty()
            else None
        )
        original_host_id = self._loaded_host_id
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
        if pending is not None:
            if original_host_id in ids:
                with picker.prevent(Select.Changed):
                    picker.value = original_host_id
            else:
                self.set_status(
                    "The edited host is no longer available. Keep editing or "
                    "explicitly discard before choosing another host."
                )
            self._restore_host_form_values(pending)
            self._refresh_host_order()
            return
        if preferred_host_id in ids:
            picker.value = preferred_host_id
        elif records and (not isinstance(picker.value, str) or picker.value not in ids):
            picker.value = records[0].id
        self._load_selected_host()
        self._refresh_host_order()

    def _load_selected_host(self) -> None:
        record = self._selected_host_record()
        if record is None or record.id != self._last_created_host_id:
            # Loading any other host ends the double-submit window of the last Create.
            self._last_created_host_signature = None
            self._last_created_host_id = None
        details = self.query_one("#guided-host-details", Static)
        if record is None:
            self._loaded_host_id = None
            self._loaded_host_record = None
            details.update("No host selected.")
            return
        host = HostProfile.from_record(record)
        self._loaded_host_id = record.id
        self._loaded_host_record = record
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
        for index, host_id in enumerate(self._selected_host_ids, start=1):
            record = repository.get_host(host_id)
            if record is None or record.project_id != project_id:
                # A display refresh is not a user-authorized membership edit.
                # Keep the missing/foreign ID in the pending order so the
                # production save can reject it instead of silently dropping it.
                rows.append(f"{index}. Unavailable host — remove or restore before saving.")
                continue
            rows.append(
                f"{index}. {record.display_name} — {record.role or 'Host'} — "
                f"{self._voice_label(record.tts_provider, record.tts_voice)}"
            )
        output.update("Episode host order:\n" + "\n".join(rows))

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
        # Host list/detail rendering runs on Textual's UI thread. ElevenLabs
        # voices() performs a remote GET and must only run for an explicit
        # discovery/preview action, never during a synchronous display refresh.
        config = self.context.composition.provider_controller.config()
        configured = config.providers.get(provider_id)
        if configured is not None and configured.provider_type == "elevenlabs":
            return f"ElevenLabs voice ({voice_id})"
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

    def _host_form_values(self) -> tuple[str, str, str, str, object]:
        return (
            self.query_one("#guided-host-name", Input).value,
            self.query_one("#guided-host-role", Input).value,
            self.query_one("#guided-host-expertise", Input).value,
            self.query_one("#guided-host-instructions", Input).value,
            self.query_one("#guided-host-preset", Select).value,
        )

    def _restore_host_form_values(
        self,
        values: tuple[str, str, str, str, object],
    ) -> None:
        name, role, expertise, instructions, preset = values
        self.query_one("#guided-host-name", Input).value = name
        self.query_one("#guided-host-role", Input).value = role
        self.query_one("#guided-host-expertise", Input).value = expertise
        self.query_one("#guided-host-instructions", Input).value = instructions
        self._assign_select(self.query_one("#guided-host-preset", Select), preset)

    def _host_profile_values_dirty(
        self,
        values: tuple[str, str, str, str, object],
    ) -> bool:
        baseline = self._form_baselines.get("hosts")
        candidate = tuple(
            zip(
                (
                    "guided-host-name",
                    "guided-host-role",
                    "guided-host-expertise",
                    "guided-host-instructions",
                ),
                values[:4],
                strict=True,
            )
        )
        if baseline is None:
            return bool(candidate)
        durable_profile = tuple(item for item in baseline if item[0] != "__episode_host_order__")
        return candidate != durable_profile

    def _host_profile_dirty(self) -> bool:
        if self.context.state.current_step != "hosts":
            return False
        return self._host_profile_values_dirty(self._host_form_values())
