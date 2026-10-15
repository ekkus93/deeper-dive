"""Episode library TUI for independent durable episode/run state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static

from deeper_dive.audio_playback import PlaybackState
from deeper_dive.diagnostics import redact
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeExportResult, EpisodeLibraryExportService
from deeper_dive.generation_monitor import GenerationMonitorScreen
from deeper_dive.screen_guard import report_service_errors, tolerate_refresh_errors
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.transcript_review_screen import TranscriptReviewScreen
from deeper_dive.user_errors import user_status

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
        config = service.load_configuration(episode_id, drop_invalid_model_overrides=True)
        return service.create(project_id, replace(config, title=f"{config.title} Copy"))

    @staticmethod
    def resume(app: DeeperDiveApp, item: EpisodeLibraryItem) -> GenerationRunRecord:
        project_id = EpisodeLibraryController._project_id(app)
        if item.episode.project_id != project_id:
            raise ValueError("selected episode does not belong to the open project")
        if item.run is None:
            raise ValueError("selected episode has no generation run to resume")
        if item.run.episode_id != item.episode.id:
            raise ValueError("selected generation run does not belong to the episode")
        # A screen selection may outlive a run transition. Do not resume a
        # stale paused snapshot or change the current selection on failure.
        current = app.service.runs(project_id).get(item.run.id)
        if current is None or current.episode_id != item.episode.id:
            raise ValueError("selected generation run is no longer available")
        if current.state != "paused":
            raise ValueError(f"run state {current.state} is not resumable")
        resumed = app.generation_monitor_controller.resume(app, current)
        app.current_episode_id = item.episode.id
        app.current_run_id = resumed.id
        return resumed

    @staticmethod
    def export(app: DeeperDiveApp, item: EpisodeLibraryItem) -> EpisodeExportResult:
        project_id = EpisodeLibraryController._project_id(app)
        return EpisodeLibraryExportService(app.service.workspaces).export(
            project_id, item.episode, item.run
        )

    @staticmethod
    def play(app: DeeperDiveApp, item: EpisodeLibraryItem) -> PlaybackState:
        audio = EpisodeLibraryController.audio_path(app, item)
        # A playback backend may fail after audio lookup. Do not publish a
        # different episode/run selection unless the operation has returned.
        state = app.composition.playback_controller.play(audio)
        app.current_episode_id = item.episode.id
        app.current_run_id = item.run.id if item.run is not None else None
        return state

    @staticmethod
    def audio_path(app: DeeperDiveApp, item: EpisodeLibraryItem) -> Path:
        project_id = EpisodeLibraryController._project_id(app)
        if item.episode.project_id != project_id:
            raise ValueError("selected episode does not belong to the open project")
        if item.run is None:
            raise ValueError("selected episode has no generation run to play")
        if item.run.episode_id != item.episode.id:
            raise ValueError("selected generation run does not belong to the episode")
        if item.run.state != "completed":
            raise ValueError(f"run state {item.run.state} is not playable")
        output = app.service.workspaces.project_root(project_id) / "output"
        for suffix in (".mp3", ".wav"):
            candidate = output / f"{item.episode.id}{suffix}"
            if candidate.is_file():
                return candidate
        raise ValueError("selected episode has no completed audio file to play")

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
    def _project_id(app: DeeperDiveApp) -> str:
        if app.current_project_id is None:
            raise RuntimeError("no project open")
        return app.current_project_id


class EpisodeLibraryScreen(Screen[None]):
    """List and manage episodes without conflating their generation runs."""

    BINDINGS = [
        Binding("p", "play_selected", "Play"),
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
        self.pending_delete_project_id: str | None = None

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
            yield Static("", id="episode-library-list", markup=False)
            yield Static("", id="episode-library-selection", markup=False)
            yield Button("Play", name="play-episode")
            yield Button("Open / Review", name="open-episode")
            yield Button("Resume", name="resume-episode")
            yield Button("Duplicate Configuration", name="duplicate-episode")
            yield Button("Export", name="export-episode")
            yield Button("Delete", name="request-delete-episode")
            yield Button("Confirm Delete", name="confirm-delete-episode")
            yield Button("Cancel Delete", name="cancel-delete-episode")
            yield Button("New Episode", name="new-episode")
            yield Static("Status: Ready", id="screen-status", markup=False)
        yield Footer()

    @report_service_errors("Library unavailable")
    def on_mount(self) -> None:
        self.refresh_library()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        actions = {
            "play-episode": self.action_play_selected,
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

    @report_service_errors("Playback failed")
    def action_play_selected(self) -> None:
        item = self._selected()
        if item is None:
            self._status("No episode selected")
            return
        try:
            state = EpisodeLibraryController.play(self._app, item)
        except ValueError as exc:
            self._status(str(exc).capitalize())
            return
        except Exception as exc:
            self._status(user_status("playback", exc))
            return
        self._status(state.message)

    @report_service_errors("Not opened")
    def action_open_selected(self) -> None:
        item = self._selected()
        if item is None:
            self._status("No episode selected")
            return
        self._app.current_episode_id = item.episode.id
        self._app.current_run_id = None if item.run is None else item.run.id
        self.app.push_screen(TranscriptReviewScreen())

    @report_service_errors("Resume failed")
    def action_resume_selected(self) -> None:
        item = self._selected()
        if item is None:
            self._status("No episode selected")
            return
        try:
            run = EpisodeLibraryController.resume(self._app, item)
        except ValueError as exc:
            self._status(str(exc).capitalize())
            return
        except Exception as exc:
            self._status(user_status("resume", exc))
            return
        self._app.current_run_id = run.id
        self._app.action_navigate("monitor")
        self.call_after_refresh(self._start_monitor_generation)

    def _start_monitor_generation(self) -> None:
        screen = self.app.screen
        if isinstance(screen, GenerationMonitorScreen):
            screen.start_background_generation()

    @report_service_errors("Not duplicated")
    def action_duplicate_selected(self) -> None:
        item = self._selected()
        if item is None:
            self._status("No episode selected")
            return
        duplicate = EpisodeLibraryController.duplicate(self._app, item.episode.id)
        self.selected_episode_id = duplicate.id
        self.refresh_library(
            f"Duplicated configuration as {duplicate.title}; invalid stored model overrides "
            "were cleared."
        )

    @report_service_errors("Export failed")
    def action_export_selected(self) -> None:
        item = self._selected()
        if item is None:
            self._status("No episode selected")
            return
        try:
            result = EpisodeLibraryController.export(self._app, item)
        except ValueError as exc:
            self._status(str(exc).capitalize())
            return
        except Exception as exc:
            self._status(user_status("export", exc))
            return
        self._status("Exported: " + ", ".join(str(path) for path in result.paths))

    @report_service_errors("Delete not requested")
    def action_request_delete(self) -> None:
        if self._selected() is None:
            self._status("No episode selected")
            return
        self.pending_delete_episode_id = self.selected_episode_id
        self.pending_delete_project_id = self._app.current_project_id
        self._status("Confirm episode deletion with Y, or cancel with Esc")

    @report_service_errors("Not deleted")
    def action_confirm_delete(self) -> None:
        episode_id = self.pending_delete_episode_id
        if episode_id is None:
            return
        project_id = self.pending_delete_project_id
        self.pending_delete_episode_id = None
        self.pending_delete_project_id = None
        # Confirmation is one-shot and scoped to both project and selection.
        # A stale confirmation must not delete a different visible record.
        if (
            project_id != self._app.current_project_id
            or episode_id != self.selected_episode_id
            or self._selected() is None
        ):
            self._status("Episode deletion cancelled because selection or project changed")
            return
        try:
            EpisodeLibraryController.delete(self._app, episode_id)
        except KeyError:
            self.refresh_library("Selected episode is no longer available")
            return
        if self._app.current_episode_id == episode_id:
            self._app.current_episode_id = None
            self._app.current_run_id = None
        self.selected_episode_id = None
        self.refresh_library("Deleted episode")

    def action_cancel_delete(self) -> None:
        if self.pending_delete_episode_id is not None:
            self.pending_delete_episode_id = None
            self.pending_delete_project_id = None
            self._status("Delete cancelled")

    def action_new_episode(self) -> None:
        self._app.current_episode_id = None
        self._app.current_run_id = None
        self._app.action_navigate("episode")

    @tolerate_refresh_errors
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
        self.query_one("#screen-status", Static).update(str(redact(f"Status: {message}")))
