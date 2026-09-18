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
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.user_config import UserConfigStore
from deeper_dive.storage.repositories import SourceRecord
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


class SourcesScreen(NavigationMixin, Screen[None]):
    """Sources workflow with grouped list, inspection, and import actions."""

    BINDINGS = [
        Binding("ctrl+a", "add_paste", "Add pasted source"),
        Binding("ctrl+f", "add_files", "Add files/directories"),
        Binding("ctrl+u", "add_urls", "Add URLs"),
        Binding("ctrl+i", "toggle_included", "Include/exclude"),
        Binding("ctrl+d", "delete_selected", "Delete source"),
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
            yield Static(
                "Primary and supplemental sources with provenance.", id="screen-description"
            )
            yield Input(placeholder="Pasted source title", id="source-title")
            yield Input(placeholder="Paste text source", id="source-text")
            yield Button("Add Paste", id="action-add-paste", name="add-paste")
            yield Input(placeholder="File or directory paths, comma separated", id="source-paths")
            yield Button("Add Files/Directory", id="action-add-files", name="add-files")
            yield Input(placeholder="Explicit URLs, comma separated", id="source-urls")
            yield Button("Add URLs", id="action-add-urls", name="add-urls")
            yield Button("Include/Exclude", id="action-toggle-source", name="toggle-source")
            yield Button("Delete Source", id="action-delete-source", name="delete-source")
            yield Static("", id="source-list")
            yield Static("", id="source-details")
            yield Static("", id="source-text-preview")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_sources()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name
        if action == "add-paste":
            self.action_add_paste()
        elif action == "add-files":
            self.action_add_files()
        elif action == "add-urls":
            self.action_add_urls()
        elif action == "toggle-source":
            self.action_toggle_included()
        elif action == "delete-source":
            self.action_delete_selected()
        else:
            super().on_button_pressed(event)

    def action_add_paste(self) -> None:
        project_id = self._project_id_or_status()
        if project_id is None:
            return
        title_input = self.query_one("#source-title", Input)
        text_input = self.query_one("#source-text", Input)
        title = title_input.value.strip() or "Pasted text"
        text = text_input.value
        if not text.strip():
            self._set_status("Pasted source text required")
            return
        source = self._app.service.add_pasted_source(project_id, title, text)
        self.selected_source_id = source.id
        title_input.value = ""
        text_input.value = ""
        self.refresh_sources(f"Added source: {source.title}")

    def action_add_files(self) -> None:
        project_id = self._project_id_or_status()
        if project_id is None:
            return
        paths_input = self.query_one("#source-paths", Input)
        paths = [Path(value.strip()) for value in paths_input.value.split(",") if value.strip()]
        if not paths:
            self._set_status("At least one file or directory path required")
            return
        summary = self._app.service.add_file_sources(project_id, paths)
        paths_input.value = ""
        if summary.imported:
            self.selected_source_id = summary.imported[0].id
        self.refresh_sources(self._summary_status(summary))

    def action_add_urls(self) -> None:
        project_id = self._project_id_or_status()
        if project_id is None:
            return
        urls_input = self.query_one("#source-urls", Input)
        urls = [value.strip() for value in urls_input.value.split(",") if value.strip()]
        if not urls:
            self._set_status("At least one HTTP/HTTPS URL required")
            return
        summary = self._app.service.add_url_sources(project_id, urls)
        urls_input.value = ""
        if summary.imported:
            self.selected_source_id = summary.imported[0].id
        self.refresh_sources(self._summary_status(summary))

    def action_toggle_included(self) -> None:
        source = self._selected_source()
        if source is None:
            self._set_status("No source selected")
            return
        project_id = self._app.current_project_id
        assert project_id is not None
        self._app.service.set_source_included(project_id, source.id, not source.included)
        self.refresh_sources("Updated source inclusion")

    def action_delete_selected(self) -> None:
        source = self._selected_source()
        if source is None:
            self._set_status("No source selected")
            return
        project_id = self._app.current_project_id
        assert project_id is not None
        self._app.service.delete_source(project_id, source.id)
        self.selected_source_id = None
        self.refresh_sources("Deleted source")

    def refresh_sources(self, status: str = "Ready") -> None:
        project_id = self._app.current_project_id
        if project_id is None:
            self.query_one("#source-list", Static).update("No project open.")
            self.query_one("#source-details", Static).update("Open a project from Home first.")
            self.query_one("#source-text-preview", Static).update("")
            self._set_status("No project open")
            return
        sources = self._app.service.list_sources(project_id)
        ids = {source.id for source in sources}
        if self.selected_source_id not in ids:
            self.selected_source_id = sources[0].id if sources else None
        self.query_one("#source-list", Static).update(self._source_list_text(sources))
        self.query_one("#source-details", Static).update(self._details_text())
        self.query_one("#source-text-preview", Static).update(self._preview_text())
        self._set_status(status)

    def _project_id_or_status(self) -> str | None:
        project_id = self._app.current_project_id
        if project_id is None:
            self._set_status("Open a project before adding sources")
            return None
        return project_id

    def _source_list_text(self, sources: list[SourceRecord]) -> str:
        if not sources:
            return "No sources yet. Paste text, add files/directories, or add URLs."
        primary = [source for source in sources if source.origin == "user"]
        supplemental = [source for source in sources if source.origin == "supplemental"]
        return "\n".join(
            (
                "Primary sources:",
                *self._source_rows(primary),
                "Supplemental sources:",
                *self._source_rows(supplemental),
            )
        )

    def _source_rows(self, sources: list[SourceRecord]) -> list[str]:
        if not sources:
            return ["  none"]
        rows = []
        for source in sources:
            selected = "*" if source.id == self.selected_source_id else " "
            included = "included" if source.included else "excluded"
            rows.append(
                f"{selected} {source.title} | {included} | {source.status} | {source.source_type}"
            )
        return rows

    def _selected_source(self) -> SourceRecord | None:
        project_id = self._app.current_project_id
        if project_id is None or self.selected_source_id is None:
            return None
        return self._app.service.get_source(project_id, self.selected_source_id)

    def _details_text(self) -> str:
        source = self._selected_source()
        if source is None:
            return "No source selected."
        return "\n".join(
            (
                f"Title: {source.title}",
                f"Origin: {source.origin}",
                f"Type: {source.source_type}",
                f"Status: {source.status}",
                f"Included: {source.included}",
                f"Locator: {source.locator or 'none'}",
                f"Content hash: {source.content_hash or 'none'}",
            )
        )

    def _preview_text(self) -> str:
        project_id = self._app.current_project_id
        source = self._selected_source()
        if project_id is None or source is None:
            return ""
        chunks = self._app.service.list_source_chunks(project_id, source.id)
        if not chunks:
            return "Parsed text: no chunks available"
        first = chunks[0]
        preview = first.text[:240]
        return f"Parsed text ({first.location or 'unknown'}): {preview}"

    def _summary_status(self, summary: SourceImportSummary) -> str:
        imported = len(summary.imported)
        skipped = len(summary.plan.candidates) - imported
        duplicate_bits = [
            f"{candidate.title}: {candidate.disposition.value}"
            for candidate in summary.plan.candidates
            if not candidate.should_import
        ]
        details = "; ".join(duplicate_bits)
        if details:
            return f"Imported {imported}; skipped {skipped}; {details}"
        return f"Imported {imported}; skipped {skipped}"

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
        "providers": lambda: ProvidersScreen(),
        "settings": lambda: ShellScreen("settings", "Settings", "Application preferences."),
        "help": lambda: ShellScreen(
            "help", "Help", "Use the footer, keyboard shortcuts, or command palette to navigate."
        ),
        "sources": lambda: SourcesScreen(),
        "research": lambda: ShellScreen("research", "Research", "Research gaps and web evidence."),
        "hosts": lambda: ShellScreen("hosts", "Hosts", "Conversation host profiles."),
        "episode": lambda: ShellScreen("episode", "Episode", "Episode configuration and plan."),
        "generate": lambda: ShellScreen("generate", "Generate", "Preflight and generation status."),
        "library": lambda: ShellScreen("library", "Library", "Generated episodes and exports."),
    }

    def __init__(
        self,
        service: DeeperDiveService | None = None,
        *,
        provider_controller: ProviderController | None = None,
    ) -> None:
        super().__init__()
        self.service = service if service is not None else DeeperDiveService(WorkspaceManager())
        self.provider_controller = provider_controller or ProviderController(
            UserConfigStore(self.service.workspaces.data_dir / "config.json"),
            LLMProviderRegistry(),
            {},
        )
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
