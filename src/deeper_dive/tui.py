"""Textual application shell for Deeper Dive."""

from __future__ import annotations

from typing import cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.application.service import DeeperDiveService, ProjectSummary
from deeper_dive.storage.workspace import WorkspaceManager

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
            self.selected_project_id = summaries[0].id if summaries else None
        self.query_one("#project-list", Static).update(self._project_list_text(summaries))
        self.query_one("#selected-project", Static).update(
            f"Selected: {self._selected_name(summaries)}"
        )
        self._set_status(status)

    def _project_list_text(self, summaries: list[ProjectSummary]) -> str:
        if not summaries:
            return "No projects yet. Enter a name and choose New Project."
        lines = []
        for summary in summaries:
            selected = "*" if summary.id == self.selected_project_id else " "
            lines.append(
                f"{selected} {summary.name} | modified {summary.modified_at} | "
                f"sources {summary.source_count} | episodes {summary.episode_count} | "
                f"status {summary.run_status}"
            )
        return "\n".join(lines)

    def _selected_name(self, summaries: list[ProjectSummary]) -> str:
        for summary in summaries:
            if summary.id == self.selected_project_id:
                return f"{summary.name} ({summary.id})"
        return "none"

    def _set_status(self, value: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {value}")


class ShellScreen(NavigationMixin, Screen[None]):
    """Simple named destination used until feature-specific screens replace the shell."""

    def __init__(self, key: str, title: str, description: str) -> None:
        super().__init__(id=f"screen-{key}")
        self.key = key
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
        "providers": lambda: ShellScreen(
            "providers", "Providers", "Configure language-model and speech providers."
        ),
        "settings": lambda: ShellScreen("settings", "Settings", "Application preferences."),
        "help": lambda: ShellScreen(
            "help", "Help", "Use the footer, keyboard shortcuts, or command palette to navigate."
        ),
        "sources": lambda: ShellScreen("sources", "Sources", "Primary and supplemental sources."),
        "research": lambda: ShellScreen("research", "Research", "Research gaps and web evidence."),
        "hosts": lambda: ShellScreen("hosts", "Hosts", "Conversation host profiles."),
        "episode": lambda: ShellScreen("episode", "Episode", "Episode configuration and plan."),
        "generate": lambda: ShellScreen("generate", "Generate", "Preflight and generation status."),
        "library": lambda: ShellScreen("library", "Library", "Generated episodes and exports."),
    }

    def __init__(self, service: DeeperDiveService | None = None) -> None:
        super().__init__()
        self.service = service if service is not None else DeeperDiveService(WorkspaceManager())
        self.current_project_id: str | None = None
        self.current_project_name: str | None = None

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
