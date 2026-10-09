"""Episode Ready: episode/run-scoped result actions via production services."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static

from deeper_dive.diagnostics import redact
from deeper_dive.episode_library_screen import (
    EpisodeLibraryController,
    EpisodeLibraryItem,
    EpisodeLibraryScreen,
)
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_workflow import WizardContext, WizardKind
from deeper_dive.transcript_review_screen import TranscriptReviewScreen
from deeper_dive.user_errors import user_status

if TYPE_CHECKING:
    from deeper_dive.tui import DeeperDiveApp


class GuidedEpisodeReadyScreen(Screen[None]):
    """Resolve all result actions against the selected durable episode and run."""

    def __init__(self) -> None:
        super().__init__(id="screen-episode-ready")

    @property
    def _app(self) -> DeeperDiveApp:
        return cast("DeeperDiveApp", self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="content"):
            yield Label("Your Deep Dive Is Ready", id="screen-title")
            yield Static("", id="ready-summary")
            yield Button("Play Episode", id="ready-play", name="ready-play")
            yield Button("Open in Review", id="ready-review", name="ready-review")
            yield Button("Export Episode", id="ready-export", name="ready-export")
            yield Button("View in Library", id="ready-library", name="ready-library")
            yield Button("Home", id="ready-home", name="ready-home")
            yield Static("", id="ready-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_ready()

    def on_screen_resume(self) -> None:
        self.refresh_ready()

    def _selected(self) -> EpisodeLibraryItem | None:
        project_id = self._app.current_project_id
        episode_id = self._app.current_episode_id
        run_id = self._app.current_run_id
        if project_id is None or episode_id is None or run_id is None:
            return None
        episode = self._app.service.hosts(project_id).get_episode(episode_id)
        run = self._app.service.runs(project_id).get(run_id)
        if (
            episode is None
            or episode.project_id != project_id
            or run is None
            or run.episode_id != episode_id
            or run.state != "completed"
        ):
            return None
        return EpisodeLibraryItem(episode, run)

    def refresh_ready(self) -> None:
        item = self._selected()
        summary = self.query_one("#ready-summary", Static)
        if item is None:
            summary.update("No completed episode/run is selected.")
        else:
            # Clear only the draft for the exact episode that this guided flow
            # just completed. Opening an unrelated Library item must not erase it.
            context = getattr(self._app, "_new_context", None)
            store = getattr(self._app, "_draft_store", None)
            if (
                isinstance(context, WizardContext)
                and isinstance(store, GuidedDraftStore)
                and context.project_id == item.episode.project_id
                and context.episode_id == item.episode.id
            ):
                store.clear(WizardKind.NEW_DEEP_DIVE)
            project_id = item.episode.project_id
            repository = self._app.service.hosts(project_id)
            hosts = [
                repository.get_host(host_id)
                for host_id in repository.list_episode_host_ids(item.episode.id)
            ]
            names = ", ".join(host.display_name for host in hosts if host is not None)
            target = item.episode.target_duration_seconds // 60
            summary.update(
                str(
                    redact(
                        f"{item.episode.title}\n"
                        f"Hosts: {names or 'none'}\n"
                        f"Target duration: {target} minutes\n"
                        f"Generation status: completed"
                    )
                )
            )
        for button_id in ("#ready-play", "#ready-review", "#ready-export", "#ready-library"):
            self.query_one(button_id, Button).disabled = item is None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name
        if action == "ready-home":
            self._app.action_navigate("home")
        elif action == "ready-review":
            if self._selected() is not None:
                self.app.push_screen(TranscriptReviewScreen())
        elif action == "ready-library":
            item = self._selected()
            if item is not None:
                library = self.app.get_screen("library")
                if isinstance(library, EpisodeLibraryScreen):
                    library.selected_episode_id = item.episode.id
                self._app.action_navigate("library")
        elif action == "ready-export":
            item = self._selected()
            if item is None:
                return
            try:
                output = EpisodeLibraryController.export(self._app, item)
                self._status("Exported: " + ", ".join(str(p) for p in output.paths))
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                self._status(user_status("export", exc))
        elif action == "ready-play":
            item = self._selected()
            if item is None:
                return
            try:
                state = EpisodeLibraryController.play(self._app, item)
                self._status(state.message)
            except (OSError, RuntimeError, ValueError) as exc:
                self._status(user_status("playback", exc))

    def _status(self, message: str) -> None:
        self.query_one("#ready-status", Static).update(str(redact(message)))
