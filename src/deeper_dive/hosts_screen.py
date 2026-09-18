"""Host profile editor screen for the Textual interface."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.hosts import HostProfile, HostRelationship, create_host_from_preset, preset_names
from deeper_dive.storage.episode_repositories import HostEpisodeRepository

if TYPE_CHECKING:
    from deeper_dive.tui import DeeperDiveApp


class HostsScreen(Screen[None]):
    """Project host list/editor with relationships and TTS voice hooks."""

    def __init__(self) -> None:
        super().__init__(id="screen-hosts")
        self.selected_host_id: str | None = None
        self.display_order: list[str] = []

    @property
    def _app(self) -> DeeperDiveApp:
        return cast("DeeperDiveApp", self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in ("home", "providers", "settings", "help"):
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with Horizontal(id="project-nav"):
            for key in ("sources", "research", "hosts", "episode", "generate", "library"):
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with VerticalScroll(id="content"):
            yield Label("Hosts", id="screen-title")
            yield Static("Create and tune conversation hosts; host count is not fixed.", id="screen-description")
            yield Static("", id="host-list")
            yield Input(value="custom", placeholder="Preset", id="host-preset")
            yield Input(placeholder="Display name", id="host-name")
            yield Input(placeholder="Role", id="host-role")
            yield Input(placeholder="Expertise", id="host-expertise")
            yield Input(placeholder="Custom instructions", id="host-instructions")
            yield Input(placeholder="Evidence priorities, comma separated", id="host-evidence")
            yield Input(placeholder="Behavior JSON", id="host-behavior")
            yield Input(placeholder="TTS provider", id="host-tts-provider")
            yield Input(placeholder="TTS voice", id="host-tts-voice")
            with Horizontal():
                for label, name in (("Add", "add-host"), ("Save", "save-host"), ("Duplicate", "duplicate-host"),
                                    ("Remove", "remove-host"), ("Up", "move-up"), ("Down", "move-down")):
                    yield Button(label, name=name)
            yield Input(placeholder="Relationship target host ID", id="relationship-target")
            yield Input(value="peer", placeholder="Relationship stance", id="relationship-stance")
            yield Input(placeholder="Relationship instructions", id="relationship-instructions")
            yield Button("Save Relationship", name="save-relationship")
            yield Button("Preview Voice", name="preview-voice")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_hosts()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "add-host": self.action_add_host, "save-host": self.action_save_host,
            "duplicate-host": self.action_duplicate_host, "remove-host": self.action_remove_host,
            "move-up": lambda: self._move(-1), "move-down": lambda: self._move(1),
            "save-relationship": self.action_save_relationship, "preview-voice": self.action_preview_voice,
        }
        name = event.button.name or ""
        if name in actions:
            actions[name]()
        elif name:
            self._app.action_navigate(name)

    def _repository(self) -> HostEpisodeRepository | None:
        project_id = self._app.current_project_id
        if project_id is None:
            self._status("Open a project first")
            return None
        return self._app.service.hosts(project_id)

    def refresh_hosts(self, status: str = "Ready") -> None:
        repository = self._repository()
        project_id = self._app.current_project_id
        if repository is None or project_id is None:
            self.query_one("#host-list", Static).update("No project open.")
            return
        records = repository.list_hosts(project_id)
        ids = [record.id for record in records]
        self.display_order = [item for item in self.display_order if item in ids]
        self.display_order.extend(item for item in ids if item not in self.display_order)
        if self.selected_host_id not in ids:
            self.selected_host_id = self.display_order[0] if self.display_order else None
        by_id = {record.id: record for record in records}
        rows = [f"{'*' if item == self.selected_host_id else ' '} {by_id[item].display_name} [{item}]"
                for item in self.display_order]
        self.query_one("#host-list", Static).update("\n".join(rows) if rows else "No hosts yet.")
        self._load_selected()
        self._status(status)

    def _load_selected(self) -> None:
        repository = self._repository()
        if repository is None or self.selected_host_id is None:
            return
        record = repository.get_host(self.selected_host_id)
        if record is None:
            return
        host = HostProfile.from_record(record)
        values = {
            "#host-preset": host.preset_origin or "custom", "#host-name": host.display_name,
            "#host-role": host.role, "#host-expertise": host.expertise, "#host-instructions": host.instructions,
            "#host-evidence": ", ".join(host.evidence_priorities), "#host-behavior": json.dumps(host.behavior, sort_keys=True),
            "#host-tts-provider": host.tts_provider or "", "#host-tts-voice": host.tts_voice or "",
        }
        for selector, value in values.items():
            self.query_one(selector, Input).value = value

    def action_add_host(self) -> None:
        repository = self._repository()
        project_id = self._app.current_project_id
        if repository is None or project_id is None:
            return
        preset = self.query_one("#host-preset", Input).value.strip() or "custom"
        if preset not in preset_names():
            self._status(f"Unknown preset: {preset}")
            return
        host = create_host_from_preset(preset, project_id)
        name = self.query_one("#host-name", Input).value.strip()
        if name:
            host.display_name = name
        repository.create_host(host.to_record())
        self.selected_host_id = host.id
        self.refresh_hosts(f"Added {host.display_name}")

    def action_save_host(self) -> None:
        repository = self._repository()
        if repository is None or self.selected_host_id is None:
            self._status("No host selected")
            return
        current = repository.get_host(self.selected_host_id)
        if current is None:
            return
        try:
            host = HostProfile(
                current.id, current.project_id, self.query_one("#host-name", Input).value.strip(),
                preset_origin=current.preset_origin, role=self.query_one("#host-role", Input).value.strip(),
                expertise=self.query_one("#host-expertise", Input).value.strip(),
                instructions=self.query_one("#host-instructions", Input).value.strip(),
                behavior=json.loads(self.query_one("#host-behavior", Input).value or "{}"),
                evidence_priorities=[x.strip() for x in self.query_one("#host-evidence", Input).value.split(",") if x.strip()],
                tts_provider=self.query_one("#host-tts-provider", Input).value.strip() or None,
                tts_voice=self.query_one("#host-tts-voice", Input).value.strip() or None,
            )
            repository.update_host(host.to_record())
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._status(str(exc))
            return
        self.refresh_hosts("Saved host")

    def action_duplicate_host(self) -> None:
        repository = self._repository()
        if repository is None or self.selected_host_id is None:
            return
        record = repository.get_host(self.selected_host_id)
        if record is None:
            return
        duplicate = replace(record, id=str(uuid4()), display_name=f"{record.display_name} copy")
        repository.create_host(duplicate)
        self.selected_host_id = duplicate.id
        self.refresh_hosts("Duplicated host")

    def action_remove_host(self) -> None:
        repository = self._repository()
        if repository is None or self.selected_host_id is None:
            return
        repository.delete_host(self.selected_host_id)
        self.display_order = [item for item in self.display_order if item != self.selected_host_id]
        self.selected_host_id = self.display_order[0] if self.display_order else None
        self.refresh_hosts("Removed host")

    def _move(self, delta: int) -> None:
        if self.selected_host_id not in self.display_order:
            return
        index = self.display_order.index(cast(str, self.selected_host_id))
        target = max(0, min(len(self.display_order) - 1, index + delta))
        self.display_order[index], self.display_order[target] = self.display_order[target], self.display_order[index]
        self.refresh_hosts("Reordered host list")

    def action_save_relationship(self) -> None:
        repository = self._repository()
        project_id = self._app.current_project_id
        if repository is None or project_id is None or self.selected_host_id is None:
            return
        target = self.query_one("#relationship-target", Input).value.strip()
        if repository.get_host(target) is None:
            self._status("Relationship target must be a project host")
            return
        try:
            relationship = HostRelationship(
                project_id, self.selected_host_id, target,
                self.query_one("#relationship-stance", Input).value.strip() or "peer",
                self.query_one("#relationship-instructions", Input).value.strip(),
            )
            repository.upsert_relationship(relationship.to_record())
        except ValueError as exc:
            self._status(str(exc))
            return
        self._status("Saved relationship")

    def action_preview_voice(self) -> None:
        provider = self.query_one("#host-tts-provider", Input).value.strip()
        voice = self.query_one("#host-tts-voice", Input).value.strip()
        if not provider or not voice:
            self._status("Choose a TTS provider and voice first")
            return
        try:
            tts = self._app.provider_controller.tts(provider)
            healthy, message = tts.health()
            if not healthy:
                self._status(f"TTS unavailable: {message}")
                return
            if voice not in tts.voices():
                self._status(f"Unknown voice: {voice}")
                return
        except KeyError as exc:
            self._status(str(exc))
            return
        self._status(f"Voice preview hook ready: {provider}/{voice}")

    def _status(self, value: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {value}")
