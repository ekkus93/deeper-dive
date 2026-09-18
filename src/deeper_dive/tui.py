"""Textual application shell and Home/Projects workflow for Deeper Dive."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.storage.workspace import WorkspaceManager

GLOBAL_SCREENS = ("home", "providers", "settings", "help")
PROJECT_SCREENS = ("sources", "research", "hosts", "episode", "generate", "library")


class ProjectNameDialog(ModalScreen[str | None]):
    """Collect a project name for create/rename operations."""

    def __init__(self, title: str, initial: str = "") -> None:
        super().__init__()
        self.dialog_title = title
        self.initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.dialog_title)
            yield Input(value=self.initial, placeholder="Project name", id="project-name")
            with Horizontal():
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        name = self.query_one("#project-name", Input).value.strip()
        if name:
            self.dismiss(name)


class ConfirmDeleteDialog(ModalScreen[bool]):
    """Require explicit confirmation before deleting a project."""

    def __init__(self, project_name: str) -> None:
        super().__init__()
        self.project_name = project_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Delete {self.project_name}? This cannot be undone.")
            with Horizontal():
                yield Button("Delete", id="confirm-delete", variant="error")
                yield Button("Cancel", id="cancel-delete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-delete")


class HomeScreen(Screen[None]):
    """Project browser backed exclusively by the application service."""

    BINDINGS = [
        Binding("n", "new_project", "New project"),
        Binding("enter", "open_project", "Open"),
        Binding("r", "rename_project", "Rename"),
        Binding("delete", "delete_project", "Delete"),
    ]

    def __init__(self) -> None:
        super().__init__(id="screen-home")

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in GLOBAL_SCREENS:
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with Horizontal(id="project-actions"):
            yield Button("New", id="new-project")
            yield Button("Open", id="open-project")
            yield Button("Rename", id="rename-project")
            yield Button("Delete", id="delete-project")
        yield Label("Projects", id="screen-title")
        yield ListView(id="project-list")
        yield Static("Select a project or create a new one.", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_projects()

    def refresh_projects(self) -> None:
        project_list = self.query_one("#project-list", ListView)
        project_list.clear()
        for summary in self.app.service.list_project_summaries():  # type: ignore[attr-defined]
            project = summary.project
            text = (
                f"{project.name} | modified {project.modified_at} | "
                f"sources {summary.source_count} | status {summary.run_status}"
            )
            project_list.append(ListItem(Label(text), name=project.id))

    def _selected_id(self) -> str | None:
        item = self.query_one("#project-list", ListView).highlighted_child
        return None if item is None else item.name

    def on_button_pressed(self, event: Button.Pressed) -> None:
        destination = event.button.name
        if destination in GLOBAL_SCREENS and destination != "home":
            self.app.push_screen(destination)
        elif event.button.id == "new-project":
            self.action_new_project()
        elif event.button.id == "open-project":
            self.action_open_project()
        elif event.button.id == "rename-project":
            self.action_rename_project()
        elif event.button.id == "delete-project":
            self.action_delete_project()

    def action_new_project(self) -> None:
        self.app.push_screen(ProjectNameDialog("New project"), self._create_project)

    def _create_project(self, name: str | None) -> None:
        if name is not None:
            self.app.service.create_project(name)  # type: ignore[attr-defined]
            self.refresh_projects()

    def action_open_project(self) -> None:
        project_id = self._selected_id()
        if project_id is not None:
            self.app.current_project_id = project_id  # type: ignore[attr-defined]
            self.app.push_screen("sources")

    def action_rename_project(self) -> None:
        project_id = self._selected_id()
        if project_id is None:
            return
        project = self.app.service.open_project(project_id)  # type: ignore[attr-defined]
        if project is not None:
            self.app.push_screen(
                ProjectNameDialog("Rename project", project.name),
                lambda name: self._rename(project_id, name),
            )

    def _rename(self, project_id: str, name: str | None) -> None:
        if name is not None:
            self.app.service.rename_project(project_id, name)  # type: ignore[attr-defined]
            self.refresh_projects()

    def action_delete_project(self) -> None:
        project_id = self._selected_id()
        if project_id is None:
            return
        project = self.app.service.open_project(project_id)  # type: ignore[attr-defined]
        if project is not None:
            self.app.push_screen(
                ConfirmDeleteDialog(project.name),
                lambda confirmed: self._delete(project_id, confirmed),
            )

    def _delete(self, project_id: str, confirmed: bool) -> None:
        if confirmed:
            self.app.service.delete_project(project_id)  # type: ignore[attr-defined]
            self.refresh_projects()


class ShellScreen(Screen[None]):
    """Simple named destination used until feature-specific screens replace the shell."""

    def __init__(self, key: str, title: str, description: str) -> None:
        super().__init__(id=f"screen-{key}")
        self.key = key
        self.shell_title = title
        self.description = description

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in GLOBAL_SCREENS:
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with Horizontal(id="project-nav"):
            for key in PROJECT_SCREENS:
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with VerticalScroll(id="content"):
            yield Label(self.shell_title, id="screen-title")
            yield Static(self.description, id="screen-description")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        destination = event.button.name
        if destination and destination != self.key:
            self.app.push_screen(destination)


class DeeperDiveApp(App[None]):
    """Responsive keyboard-first application shell."""

    TITLE = "Deeper Dive"
    SUB_TITLE = "Evidence-grounded audio conversations"
    ENABLE_COMMAND_PALETTE = True
    CSS = """
    Screen { layout: vertical; }
    #global-nav, #project-nav, #project-actions { height: auto; padding: 0 1; }
    #global-nav Button, #project-nav Button,
    #project-actions Button { min-width: 8; margin: 0 1 0 0; }
    #content { padding: 1; }
    #screen-title { text-style: bold; margin: 1; }
    #screen-status { margin: 1; }
    #project-list { height: 1fr; margin: 0 1; }
    #dialog { width: 60; height: auto; padding: 1 2; border: round $accent; background: $surface; }
    ModalScreen { align: center middle; }
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

    def __init__(self, service: DeeperDiveService | None = None) -> None:
        super().__init__()
        self.service = service or DeeperDiveService(WorkspaceManager())
        self.current_project_id: str | None = None

    SCREENS = {
        "home": HomeScreen,
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

    def on_mount(self) -> None:
        self.push_screen("home")

    def action_navigate(self, destination: str) -> None:
        if destination in self.SCREENS:
            self.push_screen(destination)


def main() -> None:
    """Run the Textual interface."""

    DeeperDiveApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
