"""Friendly host selection for the guided New Deep Dive workflow."""

from __future__ import annotations

from dataclasses import replace

from textual.widget import Widget
from textual.widgets import Button, Input, Select, Static

from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_host_support import HostWizardSupport
from deeper_dive.hosts import HostProfile, create_host_from_preset, preset_names
from deeper_dive.voice_preview import VoicePreviewService
from deeper_dive.wizard_transitions import Transition, TransitionKind


class GuidedHostWizard(HostWizardSupport):
    """Select and order friendly host profiles without exposing raw IDs."""

    def _wizard_target(self, step: str) -> str | None:
        if step == "hosts":
            return self._loaded_host_id
        return super()._wizard_target(step)

    def _editable_snapshot(self, step: str | None = None) -> tuple[tuple[str, str], ...]:
        step = step or self.context.state.current_step
        values = list(super()._editable_snapshot(step))
        if step == "hosts":
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
        # Base-class handlers are dispatched by Textual itself (no super() call).
        if event.select.id != "guided-host-picker":
            return
        value = event.value if isinstance(event.value, str) else None
        if value is None:
            return
        if self._exit_confirmation_pending:
            # Whatever transition the open prompt guards (Back, Continue, a reselect…)
            # stays the one the user resolves; a picker change must not replace it.
            original = self._loaded_host_id
            if original is not None and event.select.value != original:
                self._assign_select(event.select, original)
            return
        # A queued event for the already-loaded target must never rehydrate its
        # durable record over current edits. The direct refresh/load path already
        # established the baseline before this message was posted.
        if value == self._loaded_host_id:
            return
        if event.value != event.select.value:
            # Ignore an obsolete different-target event after a newer selection.
            return
        if self._loaded_host_id is not None and self._host_profile_dirty():
            destination = value
            preserved = self._host_form_values()
            original_host_id = self._loaded_host_id
            self._assign_select(event.select, original_host_id)
            self._restore_host_form_values(preserved)
            self._request_dirty_transition(Transition(TransitionKind.HOST_SELECT, destination))
            return
        self._load_selected_host()
        self._remember_host_profile_baseline()

    def _remember_host_profile_baseline(self) -> None:
        if self.context.state.current_step != "hosts":
            return
        current_profile = tuple(super()._editable_snapshot())
        previous = self._form_baselines.get("hosts", ())
        order = tuple(item for item in previous if item[0] == "__episode_host_order__")
        self._form_baselines["hosts"] = (*current_profile, *order)
        self._form_baseline_targets["hosts"] = self._form_target_identity()

    @staticmethod
    def _transition_is_profile_scoped(transition: Transition | None) -> bool:
        """Host picker reselect and Create Host/Pair only concern the host profile."""

        return transition is not None and transition.kind in {
            TransitionKind.HOST_SELECT,
            TransitionKind.CREATE_HOST,
            TransitionKind.CREATE_RECOMMENDED_HOSTS,
        }

    def _request_dirty_transition(self, transition: Transition) -> None:
        super()._request_dirty_transition(transition)
        if self.context.state.current_step != "hosts":
            return
        profile = self._host_profile_dirty()
        order = self._host_order_dirty()
        if self._transition_is_profile_scoped(transition):
            scope = (
                "Discard reverts the host profile only; unsaved episode host order edits "
                "stay pending."
                if order
                else "Discard reverts the host profile."
            )
        elif profile and order:
            scope = "Discard reverts both the host profile and the episode host order."
        elif order:
            scope = "Discard reverts the episode host order."
        else:
            scope = "Discard reverts the host profile."
        self.set_status(f"{self._last_form_status} {scope}")

    def _restore_discarded_form(self) -> None:
        step_is_hosts = self.context.state.current_step == "hosts"
        previous_order = tuple(
            item
            for item in self._form_baselines.get("hosts", ())
            if item[0] == "__episode_host_order__"
        )
        super()._restore_discarded_form()
        if not step_is_hosts:
            return
        if self._transition_is_profile_scoped(self._discarding_transition):
            # Profile-only prompt: membership/order edits (and their dirty
            # baseline) must survive. The shared restore re-baselined the order
            # from the live list, so put the original baseline back.
            profile = tuple(
                item
                for item in self._form_baselines.get("hosts", ())
                if item[0] != "__episode_host_order__"
            )
            self._form_baselines["hosts"] = (*profile, *previous_order)
            return
        # Leaving the step discards both scopes. Membership lives outside the
        # widget values, so restore it from the step-entry baseline (which also
        # covers the no-episode case) before falling back to the durable store.
        restored = self._order_from_baseline(previous_order)
        if restored is not None:
            self._selected_host_ids = restored
        else:
            self._selected_host_ids = []
            self._load_episode_host_order()
        self._refresh_host_order()
        self._remember_current_form()

    def _order_from_baseline(self, order_entry: tuple[tuple[str, str], ...]) -> list[str] | None:
        if not order_entry:
            return None
        _, _, ids = order_entry[0][1].partition(":")
        return [item for item in ids.split(",") if item]

    def _host_order_dirty(self) -> bool:
        if self.context.state.current_step != "hosts":
            return False
        baseline = self._form_baselines.get("hosts")
        if baseline is None:
            return bool(self._selected_host_ids)
        durable_order = next(
            (value for key, value in baseline if key == "__episode_host_order__"),
            None,
        )
        current_order = f"{self.context.episode_id or ''}:{','.join(self._selected_host_ids)}"
        return durable_order != current_order

    def _remember_host_order_baseline(self) -> None:
        if self.context.state.current_step != "hosts":
            return
        previous = self._form_baselines.get("hosts", ())
        profile = tuple(item for item in previous if item[0] != "__episode_host_order__")
        order = (
            (
                "__episode_host_order__",
                f"{self.context.episode_id or ''}:{','.join(self._selected_host_ids)}",
            ),
        )
        self._form_baselines["hosts"] = (*profile, *order)
        self._form_baseline_targets["hosts"] = self._form_target_identity()

    def _execute_custom_transition(self, transition: Transition) -> None:
        if transition.kind is TransitionKind.CREATE_HOST:
            self.action_create_host()
            return
        if transition.kind is TransitionKind.CREATE_RECOMMENDED_HOSTS:
            self.action_create_recommended_hosts()
            return
        if transition.kind is TransitionKind.HOST_SELECT:
            host_id = transition.argument or ""
            picker = self.query_one("#guided-host-picker", Select)
            if not self._assign_select(picker, host_id):
                # The chosen host vanished while the prompt was open. Anything the
                # prompt saved is already durable; re-sync the picker and say so.
                self._refresh_hosts()
                self.set_status(
                    "The selected host is no longer available; the host list was refreshed."
                )
                return
            self._load_selected_host()
            # Re-baseline only the profile: pending membership edits stay dirty.
            self._remember_host_profile_baseline()
            return
        super()._execute_custom_transition(transition)

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
        # Textual dispatches the base-class handlers itself; no super() call.

    _MUTATING_HOST_BUTTONS = frozenset(
        {
            "recommended-hosts",
            "create-host",
            "save-host",
            "select-host",
            "host-up",
            "host-down",
            "remove-selected-host",
            "save-host-order",
        }
    )

    def _host_actions_blocked(self) -> bool:
        """Mutating host actions are inert while busy or a prompt is open."""

        if self.busy:
            return True
        if self._exit_confirmation_pending:
            self.set_status("Resolve the unsaved-changes prompt (Save, Discard or Cancel) first.")
            return True
        return False

    def _sync_actions(self) -> None:
        super()._sync_actions()
        disabled = self.busy or self._exit_confirmation_pending
        for button in self.query(Button):
            if button.name in self._MUTATING_HOST_BUTTONS:
                button.disabled = disabled

    def action_create_recommended_hosts(self) -> None:
        if self.busy or self._exit_confirmation_pending:
            return
        # Creating the pair selects a new profile and rehydrates the form.
        # Preserve unsaved edits through the shared Save / Discard / Cancel flow.
        if self.context.state.current_step == "hosts" and self._host_profile_dirty():
            self._request_dirty_transition(Transition(TransitionKind.CREATE_RECOMMENDED_HOSTS))
            return
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
        # The refresh above loads a just-persisted host profile synchronously.
        # Record only that durable profile baseline; host membership/order remains
        # dirty until action_save_host_order() succeeds.
        self._remember_host_profile_baseline()
        self.set_status("Created/selected the recommended Curious Explainer and Skeptic pair.")

    def action_create_host(self) -> bool:
        if self.busy or self._exit_confirmation_pending:
            return False
        if (
            self._loaded_host_id is not None
            and self._last_created_host_signature is not None
            and self._host_form_values() == self._last_created_host_signature
        ):
            self.set_status("That host was just created. Change the form to create another.")
            return False
        # Creating a host selects a newly persisted profile and reloads these
        # controls. Do not replace edits to the selected durable host.
        if (
            self.context.state.current_step == "hosts"
            and self._loaded_host_id is not None
            and self._host_profile_dirty()
        ):
            self._request_dirty_transition(Transition(TransitionKind.CREATE_HOST))
            return False
        project_id = self.context.project_id
        if project_id is None:
            self.set_status("Create the project before creating a host.")
            return False
        preset_value = self.query_one("#guided-host-preset", Select).value
        preset = str(preset_value)
        if preset not in preset_names():
            self.set_status("Choose a valid host preset.")
            return False
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
            return False
        self._refresh_hosts(host.id, preserve_dirty=False)
        self._remember_host_profile_baseline()
        self._last_created_host_signature = self._host_form_values()
        self.set_status(f"Created host {host.display_name}.")
        return True

    def action_save_host(self) -> bool:
        if self._host_actions_blocked():
            return False
        project_id = self.context.project_id
        record = self._selected_host_record()
        if project_id is None or record is None:
            self.set_status("Choose a host to edit.")
            return False
        try:
            baseline = self._loaded_host_record
            if baseline is None or baseline.id != record.id or baseline.project_id != project_id:
                raise ValueError("Host profile is not loaded; reopen the host before saving.")
            # Use the original form identity, not the newly read record, so a
            # stale wizard cannot silently overwrite another editor's changes.
            host = HostProfile.from_record(baseline)
            self._apply_host_form(host, clear_optional=True)
            self.context.composition.service.hosts(project_id).update_host(
                host.to_record(), expected_host=baseline
            )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Host save failed.", exc)
            return False
        self._refresh_hosts(record.id, preserve_dirty=False)
        self._remember_host_profile_baseline()
        self.set_status(f"Saved host {host.display_name}.")
        return True

    def action_select_host(self) -> None:
        if self._host_actions_blocked():
            return
        record = self._selected_host_record()
        if record is None:
            self.set_status("Choose a host to add.")
            return
        if record.id not in self._selected_host_ids:
            self._selected_host_ids.append(record.id)
        self._refresh_host_order()
        self.set_status(f"Selected {record.display_name} for this episode.")

    def action_remove_selected_host(self) -> None:
        if self._host_actions_blocked():
            return
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

    def action_save_host_order(self) -> bool:
        if self._host_actions_blocked():
            return False
        project_id = self.context.project_id
        if project_id is None or not self._selected_host_ids:
            self.set_status("Select at least one host before continuing.")
            return False
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
                # Compare against the durable order seen when this form was
                # hydrated. Loading 'current' alone would allow a stale form to
                # silently replace a different editor's membership changes.
                baseline = dict(self._form_baselines.get("hosts", ())).get("__episode_host_order__")
                if baseline is None:
                    self.set_status("Host order has not been loaded; reopen the episode.")
                    return False
                current_identity = f"{self.context.episode_id}:{','.join(current.host_ids)}"
                if baseline != current_identity:
                    self.set_status(
                        "Episode host order changed since this form was loaded; "
                        "keep your edits and reload before saving."
                    )
                    return False
                # EpisodeConfigurationRepository.update applies a separate
                # atomic config-json compare-and-swap against races after
                # this read, including the host membership snapshot.
                service.edit(
                    self.context.episode_id,
                    replace(current, host_ids=tuple(self._selected_host_ids)),
                )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Host order save failed.", exc)
            return False
        self._sync_text()
        self._remember_host_order_baseline()
        self.set_status("Saved ordered episode hosts through EpisodeConfigurationService.")
        return True

    def _move_selected_host(self, delta: int) -> None:
        if self._host_actions_blocked():
            return
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
