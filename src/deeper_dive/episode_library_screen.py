"""Episode library TUI for independent durable episode/run state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static

from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.transcript_review_screen import TranscriptReviewScreen

if TYPE_CHECKING:
    from deeper_dive.tui import DeeperDiveApp


@dataclass(frozen=True, slots=True)
class EpisodeLibraryItem:
    episode: EpisodeRecord
    run: GenerationRunRecord | None

    @property
    def state(self) -> str:
        return self.run.state if self.run is not None else self.episode.state


class EpisodeLibraryController:
    """Application-facing operations used by the episode library screen."""

    @staticmethod
    def items(app: DeeperDiveApp) -> tuple[EpisodeLibraryItem, ...]:
        project_id = app.current_project_id
        if project_id is None:
            return ()
        episodes = app.service.hosts(project_id).list_episodes(project_id)
        runs = app.service.runs(project_id)
        return tuple(
            EpisodeLibraryItem(episode, runs.latest_for_episode(episode.id)) for episode in episodes
        )

    @staticmethod
    def duplicate(app: DeeperDiveApp, episode_id: str) -> EpisodeRecord:
        project_id = EpisodeLibraryController._project_id(app)
        database = Database(app.service.workspaces.project_root(project_id) / "project.db")
        service = EpisodeConfigurationService(database, clock=app.service.clock)
        config = service.load_configuration(episode_id)
        return service.create(project_id, replace(config, title=f"{config.title} Copy"))

    @staticmethod
    def delete(app: DeeperDiveApp, episode_id: str) -> None:
        project_id = EpisodeLibraryController._project_id(app)
        database = Database(app.service.workspaces.project_root(project_id) / "project.db")
        with database.transaction() as connection:
            row = connection.execute(
                "SELECT project_id FROM episodes WHERE id=?", (episode_id,)
            ).fetchone()
            if row is None or str(row["project_id"]) != project_id:
                raise KeyError(episode_id)
            connection.execute("DELETE FROM episodes WHERE id=?", (episode_id,))

    @staticmethod
    def export_location(app: DeeperDiveApp) -> str:
        project_id = EpisodeLibraryController._project_id(app)
        return str(app.service.workspaces.project_root(project_id) / "output")

    @staticmethod
    def _project_id(app: DeeperDiveApp) -> str:
        if app.current_project_id is None:
            raise RuntimeError("no project open")
        return app.current_project_id


class EpisodeLibraryScreen(Screen[None]):
    """List and manage episodes without conflating their generation runs."""

    BINDINGS = [
        Binding("o", "open_selected", "Open/review"),
        Binding("r", "resume_selected", "Resume"),
        Binding("d", "duplicate_selected", "Duplicate"),
        Binding("e", "export_selected", "Export"),
        Binding("delete", "request_delete", "Delete"),
        Binding("y", "confirm_delete", "Confirm delete"),
        Binding("escape", "cancel_delete", "Cancel delete"),
        Binding("n", "new_episode", "New episode"),
    ]

    def __init__(self) -> None:
        super().__init__(id="screen-library")
        self.selected_episode_id: str | None = None
        self.pending_delete_episode_id: str | None = None

    @property
    def _app(self) -> DeeperDiveApp:
        return cast("DeeperDiveApp", self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in ("home", "providers", "settings", "help"):
                yield Button(key.title(), name=key)
        with Horizontal(id="project-nav"):
            for key in ("sources", "research", "hosts", "episode", "generate", "library"):
                yield Button(key.title(), name=key)
        with VerticalScroll(id="content"):
            yield Label("Episode Library", id="screen-title")
            yield Static(
                "Complete, draft, failed, and paused episodes retain independent run state."
            )
            yield Static("", id="episode-library-list")
            yield Static("", id="episode-library-selection")
            yield Button("Open / Review", name="open-episode")
            yield Button("Resume", name="resume-episode")
            yield Button("Duplicate Configuration", name="duplicate-episode")
            yield Button("Export", name="export-episode")
            yield Button("Delete", name="request-delete-episode")
            yield Button("Confirm Delete", name="confirm-delete-episode")
            yield Button("Cancel Delete", name="cancel-delete-episode")
            yield Button("New Episode", name="new-episode")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_library()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        actions = {
            "open-episode": self.action_open_selected,
            "resume-episode": self.action_resume_selected,
            "duplicate-episode": self.action_duplicate_selected,
            "export-episode": self.action_export_selected,
            "request-delete-episode": self.action_request_delete,
            "confirm-delete-episode": self.action_confirm_delete,
            "cancel-delete-episode": self.action_cancel_delete,
            "new-episode": self.action_new_episode,
        }
        action = actions.get(name)
        if action is not None:
            action()
        elif name:
            self._app.action_navigate(name)

    def action_open_selected(self) -> None:
        item = self._selected()
        if item is None:
            self._status("No episode selected")
            return
        self._app.current_episode_id = item.episode.id
        self._app.current_run_id = None if item.run is None else item.run.id
        self.app.push_screen(TranscriptReviewScreen())

    def action_resume_selected(self) -> None:
        item = self._selected()
        if item is None or item.run is None:
            self._status("Selected episode has no generation run to resume")
            return
        if item.run.state not in {"paused", "failed", "pending"}:
            self._status(f"Run state {item.run.state} is not resumable")
            return
        self._app.current_episode_id = item.episode.id
        self._app.current_run_id = item.run.id
        self._app.action_navigate("monitor")

    def action_duplicate_selected(self) -> None:
        item = self._selected()
        if item is None:
            self._status("No episode selected")
            return
        duplicate = EpisodeLibraryController.duplicate(self._app, item.episode.id)
        self.selected_episode_id = duplicate.id
        self.refresh_library(f"Duplicated configuration as {duplicate.title}")

    def action_export_selected(self) -> None:
        if self._selected() is None:
            self._status("No episode selected")
            return
        self._status(f"Episode exports: {EpisodeLibraryController.export_location(self._app)}")

    def action_request_delete(self) -> None:
        if self._selected() is None:
            self._status("No episode selected")
            return
        self.pending_delete_episode_id = self.selected_episode_id
        self._status("Confirm episode deletion with Y, or cancel with Esc")

    def action_confirm_delete(self) -> None:
        episode_id = self.pending_delete_episode_id
        if episode_id is None:
            return
        EpisodeLibraryController.delete(self._app, episode_id)
        if self._app.current_episode_id == episode_id:
            self._app.current_episode_id = None
            self._app.current_run_id = None
        self.selected_episode_id = None
        self.pending_delete_episode_id = None
        self.refresh_library("Deleted episode")

    def action_cancel_delete(self) -> None:
        if self.pending_delete_episode_id is not None:
            self.pending_delete_episode_id = None
            self._status("Delete cancelled")

    def action_new_episode(self) -> None:
        self._app.current_episode_id = None
        self._app.current_run_id = None
        self._app.action_navigate("episode")

    def refresh_library(self, status: str = "Ready") -> None:
        items = EpisodeLibraryController.items(self._app)
        ids = {item.episode.id for item in items}
        if self.selected_episode_id not in ids:
            self.selected_episode_id = items[0].episode.id if items else None
        if not items:
            text = "No episodes yet. Choose New Episode to configure one."
        else:
            rows = []
            for item in items:
                selected = "*" if item.episode.id == self.selected_episode_id else " "
                run = "no run" if item.run is None else f"run {item.run.id}"
                rows.append(f"{selected} {item.episode.title} | {item.state} | {run}")
            text = "\n".join(rows)
        self.query_one("#episode-library-list", Static).update(text)
        self.query_one("#episode-library-selection", Static).update(
            f"Selected: {self.selected_episode_id or 'none'}"
        )
        self._status(status)

    def _selected(self) -> EpisodeLibraryItem | None:
        for item in EpisodeLibraryController.items(self._app):
            if item.episode.id == self.selected_episode_id:
                return item
        return None

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
