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
from deeper_dive.episode_library_screen import EpisodeLibraryScreen
from deeper_dive.episode_plan_screen import EpisodePlanController, EpisodePlanScreen
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.generation_monitor import GenerationMonitorController, GenerationMonitorScreen
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.research_screen import ResearchController, ResearchScreen
from deeper_dive.storage.repositories import SourceRecord
from deeper_dive.transcript_review_screen import TranscriptReviewScreen

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
            yield Button("Create Project", id="action-create-project", name="create-project")
            yield Static("", id="project-list")
            yield Input(placeholder="Rename selected project", id="rename-project-name")
            yield Button("Open Selected", id="action-open-project", name="open-selected")
            yield Button("Rename Selected", id="action-rename-project", name="rename-selected")
            yield Button("Delete Selected", id="action-delete-project", name="delete-selected")
            yield Button("Confirm Delete", id="action-confirm-delete", name="confirm-delete")
            yield Button("Cancel Delete", id="action-cancel-delete", name="cancel-delete")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_projects()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        actions = {
            "create-project": self.action_create_project,
            "open-selected": self.action_open_selected,
            "rename-selected": self.action_rename_selected,
            "delete-selected": self.action_request_delete,
            "confirm-delete": self.action_confirm_delete,
            "cancel-delete": self.action_cancel_delete,
        }
        action = actions.get(name)
        if action is not None:
            action()
        elif name:
            self._app.action_navigate(name)

    def refresh_projects(self) -> None:
        summaries = self._app.service.list_project_summaries()
        self.query_one("#project-list", Static).update(self._list_text(summaries))
        if summaries:
            ids = {project.id for project in summaries}
            if self.selected_project_id not in ids:
                self.selected_project_id = summaries[0].id
            selected = next(
                project for project in summaries if project.id == self.selected_project_id
            )
            self.query_one("#screen-status", Static).update(
                f"Status: Selected {selected.name}"
            )
        else:
            self.selected_project_id = None
            self.query_one("#screen-status", Static).update("Status: No projects")

    def action_create_project(self) -> None:
        value = self.query_one("#new-project-name", Input).value.strip()
        if not value:
            self._set_status("Project name is required")
            return
        project = self._app.service.create_project(value)
        self.selected_project_id = project.id
        self._app.current_project_id = project.id
        self._app.current_project_name = project.name
        self.refresh_projects()

    def action_open_selected(self) -> None:
        if self.selected_project_id is None:
            self._set_status("No project selected")
            return
        project = self._app.service.open_project(self.selected_project_id)
        if project is None:
            self._set_status("Selected project no longer exists")
            self.refresh_projects()
            return
        self._app.current_project_id = project.id
        self._app.current_project_name = project.name
        self._app.action_navigate("sources")

    def action_rename_selected(self) -> None:
        if self.selected_project_id is None:
            self._set_status("No project selected")
            return
        name = self.query_one("#rename-project-name", Input).value.strip()
        if not name:
            self._set_status("Rename value is required")
            return
        project = self._app.service.rename_project(self.selected_project_id, name)
        self._app.current_project_id = project.id
        self._app.current_project_name = project.name
        self.refresh_projects()

    def action_request_delete(self) -> None:
        if self.selected_project_id is None:
            self._set_status("No project selected")
            return
        self.pending_delete_project_id = self.selected_project_id
        self._set_status("Press Confirm Delete to permanently remove the project")

    def action_confirm_delete(self) -> None:
        if self.pending_delete_project_id is None:
            self._set_status("No delete pending")
            return
        self._app.service.delete_project(self.pending_delete_project_id)
        if self._app.current_project_id == self.pending_delete_project_id:
            self._app.current_project_id = None
            self._app.current_project_name = None
        self.pending_delete_project_id = None
        self.refresh_projects()

    def action_cancel_delete(self) -> None:
        self.pending_delete_project_id = None
        self._set_status("Delete cancelled")

    def _set_status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")

    @staticmethod
    def _list_text(projects: list[ProjectSummary]) -> str:
        if not projects:
            return "No projects yet."
        rows = []
        for project in projects:
            rows.append(
                f"{project.name} [{project.id}] | sources {project.source_count} | "
                f"episodes {project.episode_count} | run {project.run_status}"
            )
        return "\n".join(rows)


class SourcesScreen(NavigationMixin, Screen[None]):
    """Sources management TUI backed by DeeperDiveService."""

    BINDINGS = [
        Binding("ctrl+a", "add_paste", "Add pasted source"),
        Binding("i", "toggle_included", "Toggle included"),
        Binding("delete", "delete_selected", "Delete selected"),
    ]

    def __init__(self) -> None:
        super().__init__(id="screen-sources")
        self.selected_source_id: str | None = None

    @property
    def _app(self) -> DeeperDiveApp:
        return cast(DeeperDiveApp, self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        yield from _nav()
        with VerticalScroll(id="content"):
            yield Label("Sources", id="screen-title")
            yield Static("Add local files, directories, URLs, or pasted notes.", id="screen-description")
            yield Input(placeholder="Title for pasted text", id="source-title")
            yield Input(placeholder="Pasted source text", id="source-text")
            yield Button("Add Pasted Text", id="action-add-paste", name="add-paste")
            yield Static("", id="source-list")
            yield Button("Toggle Included", id="action-toggle-included", name="toggle-included")
            yield Button("Delete Source", id="action-delete-source", name="delete-source")
            yield Static("", id="source-details")
            yield Static("", id="source-text-preview")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_sources()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        actions = {
            "add-paste": self.action_add_paste,
            "toggle-included": self.action_toggle_included,
            "delete-source": self.action_delete_selected,
        }
        action = actions.get(name)
        if action is not None:
            action()
        elif name:
            self._app.action_navigate(name)

    def refresh_sources(self) -> None:
        project_id = self._app.current_project_id
        if project_id is None:
            self.query_one("#source-list", Static).update("Open a project first.")
            self.query_one("#screen-status", Static).update("Status: No project")
            return
        sources = self._app.service.list_sources(project_id)
        if not sources:
            self.selected_source_id = None
            self.query_one("#source-list", Static).update("No sources yet.")
            self.query_one("#source-details", Static).update("")
            self.query_one("#source-text-preview", Static).update("")
            self.query_one("#screen-status", Static).update("Status: No sources")
            return
        if self.selected_source_id not in {source.id for source in sources}:
            self.selected_source_id = sources[0].id
        lines = ["Primary sources:"]
        for source in sources:
            marker = ">" if source.id == self.selected_source_id else " "
            lines.append(
                f"{marker} {source.title} | {'included' if source.included else 'excluded'} | "
                f"{source.status} | {source.source_type}"
            )
        self.query_one("#source-list", Static).update("\n".join(lines))
        selected = self._selected_source(sources)
        if selected is None:
            return
        self.query_one("#source-details", Static).update(
            "\n".join(
                (
                    f"ID: {selected.id}",
                    f"Origin: {selected.origin}",
                    f"Locator: {selected.locator or 'n/a'}",
                    f"Imported: {selected.imported_at}",
                )
            )
        )
        chunks = self._app.service.list_source_chunks(project_id, selected.id)
        preview = "\n\n".join(chunk.text for chunk in chunks[:3]) if chunks else "No chunks indexed."
        self.query_one("#source-text-preview", Static).update(preview)
        self.query_one("#screen-status", Static).update(f"Status: Selected {selected.title}")

    def action_add_paste(self) -> None:
        project_id = self._app.current_project_id
        if project_id is None:
            self.query_one("#screen-status", Static).update("Status: Open a project first")
            return
        title = self.query_one("#source-title", Input).value.strip() or "Pasted text"
        text = self.query_one("#source-text", Input).value
        if not text.strip():
            self.query_one("#screen-status", Static).update("Status: Source text is required")
            return
        source = self._app.service.add_pasted_source(project_id, title, text)
        self.selected_source_id = source.id
        self.refresh_sources()

    def action_toggle_included(self) -> None:
        project_id = self._app.current_project_id
        if project_id is None or self.selected_source_id is None:
            self.query_one("#screen-status", Static).update("Status: No source selected")
            return
        source = self._app.service.get_source(project_id, self.selected_source_id)
        if source is None:
            self.query_one("#screen-status", Static).update("Status: Source missing")
            self.refresh_sources()
            return
        self._app.service.set_source_included(project_id, source.id, not source.included)
        self.refresh_sources()

    def action_delete_selected(self) -> None:
        project_id = self._app.current_project_id
        if project_id is None or self.selected_source_id is None:
            self.query_one("#screen-status", Static).update("Status: No source selected")
            return
        self._app.service.delete_source(project_id, self.selected_source_id)
        self.selected_source_id = None
        self.refresh_sources()

    @staticmethod
    def _selected_source(sources: list[SourceRecord]) -> SourceRecord | None:
        if not sources:
            return None
        for source in sources:
            if source.id == cast(object, SourcesScreen).selected_source_id:
                return source
        return sources[0]


class ShellScreen(NavigationMixin, Screen[None]):
    """Simple placeholder screen retaining the stable navigation shell."""

    def __init__(self, name: str, title: str, description: str) -> None:
        super().__init__(id=f"screen-{name}")
        self.shell_title = title
        self.description = description

    def compose(self) -> ComposeResult:
        yield Header()
        yield from _nav()
        with VerticalScroll(id="content"):
            yield Label(self.shell_title, id="screen-title")
            yield Static(self.description, id="screen-description")
            yield Static(self._status_text(), id="screen-status")
        yield Footer()

    def _status_text(self) -> str:
        project = cast(DeeperDiveApp, self.app).current_project_name or "none"
        return f"Status: Ready | Project: {project}"


class DeeperDiveApp(App[None]):
    """Responsive keyboard-first application shell."""

    TITLE = "Deeper Dive"
    SUB_TITLE = "Evidence-grounded audio conversations"
    ENABLE_COMMAND_PALETTE = True
    CSS = """
    Screen { layout: vertical; }
    #global-nav, #project-nav { height: auto; padding: 0 1; }
    #global-nav Button, #project-nav Button { min-width: 8; margin: 0 1 0 0; }
    #content { padding: 1; }
    #screen-title { text-style: bold; margin-bottom: 1; }
    #screen-status { margin-top: 1; }
    """
    BINDINGS = [
        Binding("h", "navigate('home')", "Home"),
        Binding("p", "navigate('providers')", "Providers"),
        Binding("s", "navigate('settings')", "Settings"),
        Binding("?", "navigate('help')", "Help"),
        Binding("1", "navigate('sources')", "Sources"),
        Binding("2", "navigate('research')", "Research"),
        Binding("3", "navigate('hosts')", "Hosts"),
        Binding("4", "navigate('episode')", "Episode"),
        Binding("5", "navigate('generate')", "Generate"),
        Binding("6", "navigate('library')", "Library"),
        Binding("ctrl+p", "command_palette", "Commands", show=True),
        Binding("q", "quit", "Quit"),
    ]
    SCREENS = {
        "providers": lambda: ProvidersScreen(),
        "settings": lambda: ShellScreen("settings", "Settings", "Application preferences."),
        "help": lambda: ShellScreen(
            "help", "Help", "Use the footer, keyboard shortcuts, or command palette to navigate."
        ),
        "sources": lambda: SourcesScreen(),
        "research": lambda: ResearchScreen(),
        "hosts": lambda: HostsScreen(),
        "episode": lambda: EpisodeSetupScreen(),
        "plan": lambda: EpisodePlanScreen(),
        "generate": lambda: PreflightScreen(),
        "monitor": lambda: GenerationMonitorScreen(),
        "review": lambda: TranscriptReviewScreen(),
        "library": lambda: EpisodeLibraryScreen(),
    }

    def __init__(
        self,
        service: DeeperDiveService | None = None,
        *,
        provider_controller: ProviderController | None = None,
        research_controller: ResearchController | None = None,
        episode_plan_controller: EpisodePlanController | None = None,
        preflight_controller: PreflightController | None = None,
        generation_monitor_controller: GenerationMonitorController | None = None,
    ) -> None:
        super().__init__()
        composition = ProductionComposition.build(service=service)
        self.service = composition.service
        self.provider_controller = provider_controller or composition.provider_controller
        self.research_controller = research_controller or composition.research_controller
        self.current_project_id: str | None = None
        self.current_project_name: str | None = None
        self.current_episode_id: str | None = None
        self.current_run_id: str | None = None
        self.episode_plan_controller = episode_plan_controller
        self.preflight_controller = preflight_controller or composition.preflight_controller
        self.generation_monitor_controller = (
            generation_monitor_controller or composition.generation_monitor_controller
        )
        self.plan_approved = False
        self.auto_generate_after_approval = False

    def on_mount(self) -> None:
        self.install_screen(HomeProjectsScreen(), name="home")
        self.push_screen("home")

    def action_navigate(self, destination: str) -> None:
        if destination == "home" or destination in self.SCREENS:
            self.push_screen(destination)


def main() -> None:
    """Run the Textual interface."""

    DeeperDiveApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
