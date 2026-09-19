"""Responsive generation monitor backed by durable run/checkpoint state."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Protocol, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static

from deeper_dive.application.events import ProgressEvent, ProgressSink
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.conversation_state import ConversationStateRepository
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord


@dataclass(frozen=True, slots=True)
class MonitorSnapshot:
    run: GenerationRunRecord | None
    stages: tuple[str, ...]
    completed_stages: frozenset[str]
    section: int | None = None
    turn: int | None = None
    recent_turns: tuple[str, ...] = ()
    tts_completed: int | None = None
    tts_total: int | None = None
    research_completed: int | None = None
    research_total: int | None = None


@dataclass(slots=True)
class GenerationMonitorController:
    """Read durable monitor state and optionally execute an injected pipeline runner."""

    runner: Callable[[str, ProgressSink], None] | None = None
    events: list[ProgressEvent] = field(default_factory=list)

    def snapshot(self, app: MonitorApp) -> MonitorSnapshot:
        project_id = app.current_project_id
        episode_id = app.current_episode_id
        if project_id is None or episode_id is None:
            return MonitorSnapshot(None, DEFAULT_STAGES, frozenset())
        repository = app.service.runs(project_id)
        run = repository.latest_for_episode(episode_id)
        if run is None:
            return MonitorSnapshot(None, DEFAULT_STAGES, frozenset())
        completed = frozenset(repository.list_completed_stages(run.id))
        database = Database(app.service.workspaces.project_root(project_id) / "project.db")
        conversation = ConversationStateRepository(database).get(episode_id)
        units = repository.list_completed_units_all(run.id)
        tts_units = [unit for unit in units if unit.stage == "tts" and unit.unit_id != "stage"]
        research_units = [
            unit for unit in units if unit.stage == "research" and unit.unit_id != "stage"
        ]
        return MonitorSnapshot(
            run,
            DEFAULT_STAGES,
            completed,
            None if conversation is None else conversation.segment_ordinal,
            None if conversation is None else conversation.segment_turn,
            self._recent_turns(app, episode_id),
            len(tts_units) if tts_units else None,
            None,
            len(research_units) if research_units else None,
            None,
        )

    async def run(self, run_id: str) -> None:
        if self.runner is None:
            raise RuntimeError("generation runner is not configured")
        await asyncio.to_thread(self.runner, run_id, self.events.append)

    @staticmethod
    def _recent_turns(app: MonitorApp, episode_id: str) -> tuple[str, ...]:
        project_id = app.current_project_id
        if project_id is None:
            return ()
        database = Database(app.service.workspaces.project_root(project_id) / "project.db")
        with database.connection() as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_turns'"
            ).fetchone()
            if table is None:
                return ()
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(conversation_turns)")
            }
            if not {"episode_id", "id"}.issubset(columns):
                return ()
            text_column = (
                "text" if "text" in columns else "content" if "content" in columns else None
            )
            if text_column is None:
                return ()
            rows = connection.execute(
                f"SELECT id,{text_column} AS body FROM conversation_turns "
                "WHERE episode_id=? ORDER BY rowid DESC LIMIT 5",
                (episode_id,),
            ).fetchall()
        return tuple(f"{row['id']}: {str(row['body'])[:160]}" for row in reversed(rows))


class MonitorApp(Protocol):
    service: DeeperDiveService
    generation_monitor_controller: GenerationMonitorController
    current_project_id: str | None
    current_episode_id: str | None
    current_run_id: str | None

    def action_navigate(self, destination: str) -> None: ...


class GenerationMonitorScreen(Screen[None]):
    """Live, non-blocking view of durable generation progress."""

    BINDINGS = [
        Binding("p", "pause", "Pause"),
        Binding("r", "resume", "Resume"),
        Binding("c", "cancel", "Cancel"),
        Binding("t", "view_transcript", "Transcript"),
        Binding("d", "diagnostics", "Diagnostics"),
    ]

    def __init__(self) -> None:
        super().__init__(id="screen-monitor")
        self._task: asyncio.Task[None] | None = None

    @property
    def _app(self) -> MonitorApp:
        return cast(MonitorApp, self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in ("home", "providers", "settings", "help"):
                yield Button(key.title(), name=key)
        with Horizontal(id="project-nav"):
            for key in ("sources", "research", "hosts", "episode", "generate", "library"):
                yield Button(key.title(), name=key)
        with VerticalScroll(id="content"):
            yield Label("Generation Monitor", id="screen-title")
            yield Static("", id="generation-state")
            yield Static("", id="stage-checklist")
            yield Static("", id="current-work")
            yield Static("", id="recent-turns")
            yield Static("", id="tts-progress")
            yield Static("", id="research-progress")
            yield Button("Pause", name="pause-generation")
            yield Button("Resume", name="resume-generation")
            yield Button("Cancel", name="cancel-generation")
            yield Button("View Transcript", name="view-transcript")
            yield Button("Diagnostics", name="diagnostics")
            yield Static("", id="diagnostics-summary")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_monitor()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        actions = {
            "pause-generation": self.action_pause,
            "resume-generation": self.action_resume,
            "cancel-generation": self.action_cancel,
            "view-transcript": self.action_view_transcript,
            "diagnostics": self.action_diagnostics,
        }
        action = actions.get(name)
        if action is not None:
            action()
        elif name:
            self._app.action_navigate(name)

    def action_pause(self) -> None:
        run = self._run()
        if run is None:
            self._status("No generation run")
            return
        self._app.service.runs(self._project_id()).request_pause(run.id, self._now())
        self.refresh_monitor("Pause requested; current provider call may finish first")

    def action_resume(self) -> None:
        run = self._run()
        if run is None:
            self._status("No generation run")
            return
        if run.cancel_requested or run.state == "cancelled":
            self._status("Cancelled runs cannot resume")
            return
        repository = self._app.service.runs(self._project_id())
        repository.update(
            replace(
                run,
                state="pending",
                pause_requested=False,
                failure_code=None,
                failure_message=None,
                modified_at=self._now(),
            )
        )
        self.refresh_monitor("Run ready to resume")

    def action_cancel(self) -> None:
        run = self._run()
        if run is None:
            self._status("No generation run")
            return
        self._app.service.runs(self._project_id()).request_cancel(run.id, self._now())
        self.refresh_monitor("Cancel requested; current provider call may finish first")

    def action_view_transcript(self) -> None:
        snapshot = self._app.generation_monitor_controller.snapshot(self._app)
        text = (
            "\n".join(snapshot.recent_turns)
            if snapshot.recent_turns
            else "Transcript not available yet."
        )
        self.query_one("#diagnostics-summary", Static).update("Transcript preview:\n" + text)

    def action_diagnostics(self) -> None:
        run = self._run()
        if run is None:
            text = "No run diagnostics available."
        else:
            text = "\n".join(
                (
                    f"Run: {run.id}",
                    f"State: {run.state}",
                    f"Stage: {run.stage}",
                    f"Retries: {run.retry_count}",
                    f"Failure: {run.failure_code or 'none'} - {run.failure_message or 'none'}",
                )
            )
        self.query_one("#diagnostics-summary", Static).update(text)

    def start_background_generation(self) -> None:
        run = self._run()
        if run is None or self._app.generation_monitor_controller.runner is None:
            return
        self._task = asyncio.create_task(self._background_run(run.id))

    async def _background_run(self, run_id: str) -> None:
        self._status("Generation running")
        try:
            await self._app.generation_monitor_controller.run(run_id)
        except Exception as exc:
            self._status(f"Generation failed: {exc}")
        else:
            self._status("Generation finished")
        self.refresh_monitor()

    def refresh_monitor(self, status: str | None = None) -> None:
        snapshot = self._app.generation_monitor_controller.snapshot(self._app)
        run = snapshot.run
        self.query_one("#generation-state", Static).update(
            "Run: none" if run is None else f"Run: {run.id} | {run.state} | stage {run.stage}"
        )
        self.query_one("#stage-checklist", Static).update(
            "Stages:\n"
            + "\n".join(
                f"{'[x]' if stage in snapshot.completed_stages else '[ ]'} {stage}"
                for stage in snapshot.stages
            )
        )
        current = "Current section/turn: not available yet"
        if snapshot.section is not None or snapshot.turn is not None:
            current = f"Current section/turn: {snapshot.section or 0} / {snapshot.turn or 0}"
        self.query_one("#current-work", Static).update(current)
        self.query_one("#recent-turns", Static).update(
            "Recent turns:\n"
            + ("\n".join(snapshot.recent_turns) if snapshot.recent_turns else "none yet")
        )
        self.query_one("#tts-progress", Static).update(
            self._progress("TTS", snapshot.tts_completed, snapshot.tts_total)
        )
        self.query_one("#research-progress", Static).update(
            self._progress("Research", snapshot.research_completed, snapshot.research_total)
        )
        if status is not None:
            self._status(status)

    @staticmethod
    def _progress(label: str, completed: int | None, total: int | None) -> str:
        if completed is None:
            return f"{label} progress: not available"
        if total is None:
            return f"{label} progress: {completed} completed unit(s)"
        return f"{label} progress: {completed}/{total}"

    def _run(self) -> GenerationRunRecord | None:
        return self._app.generation_monitor_controller.snapshot(self._app).run

    def _project_id(self) -> str:
        project_id = self._app.current_project_id
        if project_id is None:
            raise RuntimeError("no project open")
        return project_id

    def _now(self) -> str:
        from deeper_dive.domain.clock import format_timestamp

        return format_timestamp(self._app.service.clock.now())

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
