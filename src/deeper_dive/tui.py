"""Textual application shell for Deeper Dive."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.storage.workspace import WorkspaceManager

GLOBAL_SCREENS = ("home", "providers", "settings", "help")
PROJECT_SCREENS = ("sources", "research", "hosts", "episode", "generate", "library")


class NameDialog(ModalScreen[str | None]):
    """Collect a project name without coupling persistence to the widget layer."""

    def __init__(self, title: str, *, initial: str = "") -> None:
        super().__init__()
        self.dialog_title = title
        self.initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.dialog_title)
            yield Input(value=self.initial, placeholder="Project name", id="project-name")
            with Horizontal():
                yield Button("Save", id="dialog-save", variant="primary")
                yield Button("Cancel", id="dialog-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dialog-cancel":
            self.dismiss(None)
            return
        value = self.query_one("#project-name", Input).value.strip()
        if value:
            self.dismiss(value)


class DeleteDialog(ModalScreen[bool]):
    """Require explicit confirmation before deleting a project workspace."""

    def __init__(self, project_name: str) -> None:
        super().__init__()
        self.project_name = project_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Delete project '{self.project_name}'? This cannot be undone.")
            with Horizontal():
                yield Button("Delete", id="delete-confirm", variant="error")
                yield Button("Cancel", id="delete-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete-confirm")


class ShellScreen(Screen[None]):
    """Simple named destination used until feature-specific screens replace the shell."""

    def __init__(self, key: str, title: str, description: str) -> None:
        super().__init__(id=f"screen-{key}")
        self.key = key
        self.shell_title = title
        self.description = description

    def compose(self) -> ComposeResult:
        yield Header()
        yield from _navigation()
        with VerticalScroll(id="content"):
            yield Label(self.shell_title, id="screen-title")
            yield Static(self.description, id="screen-description")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        destination = event.button.name
        if destination and destination != self.key:
            self.app.push_screen(destination)


class HomeScreen(Screen[None]):
    """Project browser backed exclusively by application-service operations."""

    def __init__(self) -> None:
        super().__init__(id="screen-home")
        self.selected_project_id: str | None = None

    @property
    def service(self) -> DeeperDiveService:
        return self.app.service  # type: ignore[attr-defined,no-any-return]

    def compose(self) -> ComposeResult:
        yield Header()
        yield from _navigation()
        with VerticalScroll(id="content"):
            yield Label("Projects", id="screen-title")
            with Horizontal(id="project-actions"):
                yield Button("New", id="project-new", variant="primary")
                yield Button("Open", id="project-open")
                yield Button("Rename", id="project-rename")
                yield Button("Delete", id="project-delete")
            yield Vertical(id="project-list")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_projects()

    def refresh_projects(self) -> None:
        container = self.query_one("#project-list", Vertical)
        container.remove_children()
        summaries = self.service.project_summaries()
        if not summaries:
            container.mount(
                Static("No projects yet. Create one to begin.", id="project-empty")
            )
            self.selected_project_id = None
            return
        valid_ids = {summary.project.id for summary in summaries}
        if self.selected_project_id not in valid_ids:
            self.selected_project_id = summaries[0].project.id
        for summary in summaries:
            project = summary.project
            selected = "Selected — " if project.id == self.selected_project_id else ""
            label = (
                f"{selected}{project.name} | modified {project.modified_at} | "
                f"sources {summary.source_count} | status {summary.run_status}"
            )
            container.mount(Button(label, id=f"select-{project.id}", name=project.id))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if event.button.name in GLOBAL_SCREENS + PROJECT_SCREENS:
            self.app.push_screen(event.button.name)
        elif button_id.startswith("select-") and event.button.name:
            self.selected_project_id = event.button.name
            self.refresh_projects()
        elif button_id == "project-new":
            self.app.push_screen(NameDialog("New project"), self._created)
        elif button_id == "project-open":
            self._open_selected()
        elif button_id == "project-rename":
            self._rename_selected()
        elif button_id == "project-delete":
            self._delete_selected()

    def _created(self, name: str | None) -> None:
        if name is None:
            return
        project = self.service.create_project(name)
        self.selected_project_id = project.id
        self.refresh_projects()

    def _open_selected(self) -> None:
        if self.selected_project_id is None:
            return
        project = self.service.open_project(self.selected_project_id)
        if project is not None:
            self.app.current_project_id = project.id  # type: ignore[attr-defined]
            self.app.push_screen("sources")

    def _rename_selected(self) -> None:
        if self.selected_project_id is None:
            return
        project = self.service.open_project(self.selected_project_id)
        if project is not None:
            self.app.push_screen(
                NameDialog("Rename project", initial=project.name), self._renamed
            )

    def _renamed(self, name: str | None) -> None:
        if name is not None and self.selected_project_id is not None:
            self.service.rename_project(self.selected_project_id, name)
            self.refresh_projects()

    def _delete_selected(self) -> None:
        if self.selected_project_id is None:
            return
        project = self.service.open_project(self.selected_project_id)
        if project is not None:
            self.app.push_screen(DeleteDialog(project.name), self._deleted)

    def _deleted(self, confirmed: bool) -> None:
        if confirmed and self.selected_project_id is not None:
            self.service.delete_project(self.selected_project_id)
            self.selected_project_id = None
            self.refresh_projects()


def _navigation() -> ComposeResult:
    with Horizontal(id="global-nav"):
        for key in GLOBAL_SCREENS:
            yield Button(key.title(), id=f"nav-{key}", name=key)
    with Horizontal(id="project-nav"):
        for key in PROJECT_SCREENS:
            yield Button(key.title(), id=f"nav-{key}", name=key)


class DeeperDiveApp(App[None]):
    """Responsive keyboard-first application shell."""

    TITLE = "Deeper Dive"
    SUB_TITLE = "Evidence-grounded audio conversations"
    ENABLE_COMMAND_PALETTE = True
    CSS = """
    Screen { layout: vertical; }
    #global-nav, #project-nav, #project-actions { height: auto; padding: 0 1; }
    #global-nav Button, #project-nav Button, #project-actions Button { min-width: 8; margin: 0 1 0 0; }
    #content { padding: 1; }
    #screen-title { text-style: bold; margin-bottom: 1; }
    #screen-status { margin-top: 1; }
    #project-list { height: auto; }
    #project-list Button { width: 100%; margin-top: 1; }
    NameDialog, DeleteDialog { align: center middle; }
    #dialog { width: 60; height: auto; border: round $accent; padding: 1 2; background: $surface; }
    #dialog Horizontal { height: auto; margin-top: 1; }
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
        "home": HomeScreen,
        "providers": lambda: ShellScreen(
            "providers", "Providers", "Configure language-model and speech providers."
        ),
        "settings": lambda: ShellScreen(
            "settings", "Settings", "Application preferences."
        ),
        "help": lambda: ShellScreen(
            "help", "Help", "Use the footer, keyboard shortcuts, or command palette to navigate."
        ),
        "sources": lambda: ShellScreen(
            "sources", "Sources", "Primary and supplemental sources."
        ),
        "research": lambda: ShellScreen(
            "research", "Research", "Research gaps and web evidence."
        ),
        "hosts": lambda: ShellScreen(
            "hosts", "Hosts", "Conversation host profiles."
        ),
        "episode": lambda: ShellScreen(
            "episode", "Episode", "Episode configuration and plan."
        ),
        "generate": lambda: ShellScreen(
            "generate", "Generate", "Preflight and generation status."
        ),
        "library": lambda: ShellScreen(
            "library", "Library", "Generated episodes and exports."
        ),
    }

    def __init__(
        self,
        *,
        service: DeeperDiveService | None = None,
        data_dir: Path | str | None = None,
    ) -> None:
        super().__init__()
        self.service = service or DeeperDiveService(WorkspaceManager(data_dir))
        self.current_project_id: str | None = None

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
