"""Textual application shell for Deeper Dive."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.application.service import DeeperDiveService, ProjectSummary, SourceImportSummary
from deeper_dive.composition import ProductionComposition
from deeper_dive.destructive_confirmation import PendingRemoval
from deeper_dive.diagnostics import redact
from deeper_dive.episode_library_screen import EpisodeLibraryScreen
from deeper_dive.episode_plan_screen import EpisodePlanController, EpisodePlanScreen
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.generation_monitor import GenerationMonitorController, GenerationMonitorScreen
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.research_screen import ResearchController, ResearchScreen
from deeper_dive.settings_screen import SettingsScreen
from deeper_dive.storage.repositories import SourceRecord

GLOBAL_SCREENS = ("home", "providers", "settings", "help")
PROJECT_SCREENS = ("sources", "research", "hosts", "episode", "generate", "library")


def _nav() -> ComposeResult:
    with Horizontal(id="global-nav"):
        for key in GLOBAL_SCREENS:
            yield Button(key.title(), id=f"nav-{key}", name=key)
    with Horizontal(id="project-nav"):
        for key in PROJECT_SCREENS:
            yield Button(key.title(), id=f"nav-{key}", name=key)


class NavigationMixin:
    """Shared button navigation for shell screens."""

    @property
    def _navigation_app(self) -> DeeperDiveApp:
        return cast(DeeperDiveApp, cast(Screen[None], self).app)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        destination = event.button.name
        if destination:
            # Navigation may replace the current screen synchronously. Stop this
            # press before routing so it cannot bubble into the newly mounted screen.
            event.stop()
            self._navigation_app.action_navigate(destination)


class HomeProjectsScreen(NavigationMixin, Screen[None]):
    """Project list and project lifecycle workflow."""

    BINDINGS = [
        Binding("ctrl+n", "create_project", "New project"),
        Binding("ctrl+o", "open_selected", "Open project"),
        Binding("ctrl+r", "rename_selected", "Rename project"),
        Binding("ctrl+d", "request_delete", "Delete project"),
        Binding("y", "confirm_delete", "Confirm delete"),
        Binding("escape", "cancel_delete", "Cancel delete"),
    ]

    def __init__(self) -> None:
        super().__init__(id="screen-home")
        self.selected_project_id: str | None = None
        self.pending_delete_project_id: str | None = None

    @property
    def _app(self) -> DeeperDiveApp:
        return cast(DeeperDiveApp, self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        yield from _nav()
        with VerticalScroll(id="content"):
            yield Label("Projects", id="screen-title")
            yield Static(
                "Create, open, rename, or delete a Deeper Dive project.",
                id="screen-description",
            )
            yield Input(placeholder="New project name", id="new-project-name")
            yield Button("New Project", id="action-new-project", name="create-project")
            yield Static("", id="project-list")
            yield Static("Selected: none", id="selected-project")
            yield Input(placeholder="Rename selected project", id="rename-project-name")
            yield Button("Open", id="action-open-project", name="open-selected")
            yield Button("Rename", id="action-rename-project", name="rename-selected")
            yield Button("Delete", id="action-delete-project", name="request-delete")
            yield Button("Confirm Delete", id="action-confirm-delete", name="confirm-delete")
            yield Button("Cancel Delete", id="action-cancel-delete", name="cancel-delete")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_projects()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name
        if action == "create-project":
            self.action_create_project()
        elif action == "open-selected":
            self.action_open_selected()
        elif action == "rename-selected":
            self.action_rename_selected()
        elif action == "request-delete":
            self.action_request_delete()
        elif action == "confirm-delete":
            self.action_confirm_delete()
        elif action == "cancel-delete":
            self.action_cancel_delete()
        else:
            super().on_button_pressed(event)

    def action_create_project(self) -> None:
        name_input = self.query_one("#new-project-name", Input)
        name = name_input.value.strip()
        if not name:
            self._set_status("Project name required")
            return
        project = self._app.service.create_project(name)
        name_input.value = ""
        self.selected_project_id = project.id
        self.pending_delete_project_id = None
        self.refresh_projects(f"Created project: {project.name}")

    def action_open_selected(self) -> None:
        if self.selected_project_id is None:
            self._set_status("No project selected")
            return
        project = self._app.service.open_project(self.selected_project_id)
        if project is None:
            self.refresh_projects("Selected project no longer exists")
            return
        self._app.current_project_id = project.id
        self._app.current_project_name = project.name
        self._app.action_navigate("sources")

    def action_rename_selected(self) -> None:
        if self.selected_project_id is None:
            self._set_status("No project selected")
            return
        rename_input = self.query_one("#rename-project-name", Input)
        name = rename_input.value.strip()
        if not name:
            self._set_status("Rename requires a project name")
            return
        project = self._app.service.rename_project(self.selected_project_id, name)
        rename_input.value = ""
        self.refresh_projects(f"Renamed project: {project.name}")

    def action_request_delete(self) -> None:
        if self.selected_project_id is None:
            self._set_status("No project selected")
            return
        self.pending_delete_project_id = self.selected_project_id
        self._set_status("Confirm delete with Y, or cancel with Esc")

    def action_confirm_delete(self) -> None:
        if self.pending_delete_project_id is None:
            return
        self._app.service.delete_project(self.pending_delete_project_id)
        if self.selected_project_id == self.pending_delete_project_id:
            self.selected_project_id = None
        self.pending_delete_project_id = None
        self.refresh_projects("Deleted project")

    def action_cancel_delete(self) -> None:
        if self.pending_delete_project_id is not None:
            self.pending_delete_project_id = None
            self._set_status("Delete cancelled")

    def refresh_projects(self, status: str = "Ready") -> None:
        summaries = self._app.service.list_project_summaries()
        ids = {summary.id for summary in summaries}
        if self.selected_project_id not in ids:
