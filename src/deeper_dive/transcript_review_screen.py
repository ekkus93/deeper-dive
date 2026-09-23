"""Transcript and review TUI with claims and evidence navigation."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive import model_roles
from deeper_dive.audio_playback import AudioPlaybackController, PlaybackState
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.claim_inspector_screen import ClaimInspectorController, ClaimInspectorScreen
from deeper_dive.composition import _composition_stage, _tts_stage
from deeper_dive.host_turn import HostTurn
from deeper_dive.llm import LLMMessage, LLMProvider, LLMRequest
from deeper_dive.pipeline import PipelineContext
from deeper_dive.storage.database import Database
from deeper_dive.targeted_repair import TargetedRepairService

if TYPE_CHECKING:
    from deeper_dive.tui import DeeperDiveApp

NO_EXPORTED_AUDIO_MESSAGE = (
    "No exported audio file is available yet; generation/export are unaffected."
)


@dataclass(frozen=True, slots=True)
class TranscriptTurn:
    id: str
    segment_ordinal: int
    turn_ordinal: int
    speaker_id: str
    speaker_name: str
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TurnClaimSummary:
    id: str
    text: str
    state: str
    rationale: str
    supporting_ids: tuple[str, ...]
    contradicting_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourcePassageSummary:
    chunk_id: str
    source_title: str
    origin: str
    location: str | None
    text: str


@dataclass(frozen=True, slots=True)
class _ProductionTurnRepairProvider:
    provider: LLMProvider
    model: str | None

    def repair_turn(self, turn: HostTurn, feedback: str, evidence_ids: tuple[str, ...]) -> str:
        response = self.provider.generate(
            LLMRequest(
                messages=(
                    LLMMessage(
                        "system",
                        "Repair the selected turn. Return only the repaired text.",
                    ),
                    LLMMessage(
                        "user",
                        "\n".join(
                            (
                                f"Turn ID: {turn.id}",
                                f"Speaker ID: {turn.speaker_id}",
                                f"Original text: {turn.text}",
                                f"Repair feedback: {feedback}",
                                "Evidence IDs: " + ", ".join(evidence_ids),
                            )
                        ),
                    ),
                ),
                model=self.model,
            )
        )
        return response.text


class _NoOpRepairRechecker:
    def recheck_turn(self, turn: HostTurn) -> None:
        _ = turn


class _NoOpSummaryUpdater:
    def update_after_repair(self, episode_id: str, turn_id: str) -> None:
        _ = (episode_id, turn_id)


class TranscriptReviewController:
    """Read transcript, claim, source-passage, and playback state for review screens."""

    def __init__(
        self,
        repair: Callable[[str], object] | None = None,
        playback: AudioPlaybackController | None = None,
    ) -> None:
        self.repair_callback = repair
        self.playback = playback or AudioPlaybackController()

    def turns(self, app: DeeperDiveApp) -> tuple[TranscriptTurn, ...]:
        database = self._database(app)
        episode_id = self._episode_id(app)
        with database.connection() as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_turns'"
            ).fetchone()
            if table is None:
                return ()
            rows = connection.execute(
                """SELECT t.id,t.segment_ordinal,t.turn_ordinal,t.speaker_id,t.text,
                t.evidence_ids_json,COALESCE(h.display_name,t.speaker_id) AS speaker_name
                FROM conversation_turns t LEFT JOIN hosts h ON h.id=t.speaker_id
                WHERE t.episode_id=? ORDER BY t.segment_ordinal,t.turn_ordinal""",
                (episode_id,),
            ).fetchall()
        return tuple(self._turn_from_row(row) for row in rows)

    def claims(self, app: DeeperDiveApp, turn_id: str) -> tuple[TurnClaimSummary, ...]:
        database = self._database(app)
        with database.connection() as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='material_claims'"
            ).fetchone()
            if table is None:
                return ()
            rows = connection.execute(
                """SELECT mc.id,mc.text,cv.state,cv.rationale,
                cv.supporting_evidence_ids_json,cv.contradicting_evidence_ids_json
                FROM material_claims mc LEFT JOIN claim_verifications cv ON cv.claim_id=mc.id
                WHERE mc.turn_id=? ORDER BY mc.span_start,mc.id""",
                (turn_id,),
            ).fetchall()
        return tuple(self._claim_from_row(row) for row in rows)

    def passages(
        self, app: DeeperDiveApp, chunk_ids: tuple[str, ...]
    ) -> tuple[SourcePassageSummary, ...]:
        if not chunk_ids:
            return ()
        database = self._database(app)
        placeholders = ",".join("?" for _ in chunk_ids)
        with database.connection() as connection:
            rows = connection.execute(
                f"""SELECT c.id,c.text,c.location,s.title,s.origin
                FROM source_chunks c JOIN sources s ON s.id=c.source_id
                WHERE c.id IN ({placeholders})""",
                chunk_ids,
            ).fetchall()
        by_id = {str(row["id"]): row for row in rows}
        return tuple(
            SourcePassageSummary(
                chunk_id=chunk_id,
                source_title=str(by_id[chunk_id]["title"]),
                origin=str(by_id[chunk_id]["origin"]),
                location=self._optional_text(by_id[chunk_id]["location"]),
                text=str(by_id[chunk_id]["text"]),
            )
            for chunk_id in chunk_ids
            if chunk_id in by_id
        )

    def repair_turn(self, turn_id: str, app: DeeperDiveApp | None = None) -> object:
        if self.repair_callback is not None:
            return self.repair_callback(turn_id)
        if app is None:
            raise RuntimeError("targeted transcript repair is not configured")
        return self._production_repair(app, turn_id)

    def repair_section(self, app: DeeperDiveApp, segment_ordinal: int) -> tuple[HostTurn, ...]:
        service = self._production_repair_service(app)
        repaired = service.repair_section(self._episode_id(app), segment_ordinal)
        had_audio = self._invalidate_episode_audio(app, tuple(turn.id for turn in repaired))
        self._regenerate_episode_audio_if_required(app, had_audio)
        return repaired

    def export_markdown(self, app: DeeperDiveApp) -> Path:
        project_id = self._project_id(app)
        episode_id = self._episode_id(app)
        root = app.service.workspaces.project_root(project_id)
        path = root / "output" / f"{episode_id}-transcript-review.md"
        lines = [f"# Transcript review: {episode_id}", ""]
        for turn in self.turns(app):
            heading = (
                f"## Chapter {turn.segment_ordinal + 1} / "
                f"Turn {turn.turn_ordinal + 1}: {turn.speaker_name}"
            )
            lines.extend((heading, "", turn.text, ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def claim_inspector(self, app: DeeperDiveApp, turn_id: str) -> ClaimInspectorScreen:
        repair = self.repair_callback or (
            lambda repaired_turn_id: self.repair_turn(repaired_turn_id, app)
        )
        controller = ClaimInspectorController(self._database(app), repair)
        return ClaimInspectorScreen(controller, turn_id)

    def play_turn(self, app: DeeperDiveApp, turn: TranscriptTurn) -> PlaybackState:
        audio_path = self.audio_path(app)
        position = self.start_seconds_for_turn(app, turn.id)
        if audio_path is None:
            return PlaybackState(
                available=False,
                playing=False,
                message=NO_EXPORTED_AUDIO_MESSAGE,
                position_seconds=position,
                capabilities=self.playback.capabilities,
            )
        return self.playback.seek(audio_path, start_seconds=position)

    def pause_playback(self) -> PlaybackState:
        return self.playback.pause()

    def resume_playback(self) -> PlaybackState:
        return self.playback.resume()

    def audio_path(self, app: DeeperDiveApp) -> Path | None:
        project_id = self._project_id(app)
        episode_id = self._episode_id(app)
        output = app.service.workspaces.project_root(project_id) / "output"
        for suffix in (".mp3", ".wav"):
            candidate = output / f"{episode_id}{suffix}"
            if candidate.is_file():
                return candidate
        return None

    def start_seconds_for_turn(self, app: DeeperDiveApp, turn_id: str) -> float:
        timeline = AudioTimelineRepository(self._database(app)).get(self._episode_id(app))
        if timeline is None:
            return 0.0
        for placement in timeline.placements:
            if placement.item.turn_id == turn_id:
                return placement.start_seconds
        for chapter in timeline.chapters:
            if chapter.turn_id == turn_id:
                return chapter.start_seconds
        return 0.0

    def _production_repair(self, app: DeeperDiveApp, turn_id: str) -> HostTurn:
        service = self._production_repair_service(app)
        repaired = service.repair(turn_id)
        had_audio = self._invalidate_episode_audio(app, (turn_id,))
        self._regenerate_episode_audio_if_required(app, had_audio)
        return repaired

    def _production_repair_service(self, app: DeeperDiveApp) -> TargetedRepairService:
        composition = getattr(app.service, "_production_composition", None)
        if composition is None:
            raise RuntimeError("production targeted transcript repair is not configured")
        database = self._database(app)
        episode_id = self._episode_id(app)
        provider, model = self._repair_provider(composition, self._project_id(app), episode_id)
        return TargetedRepairService(
            database,
            _ProductionTurnRepairProvider(provider, model),
            _NoOpRepairRechecker(),
            _NoOpSummaryUpdater(),
        )

    @staticmethod
    def _repair_provider(
        composition: Any, project_id: str, episode_id: str
    ) -> tuple[LLMProvider, str | None]:
        assignments, errors = composition.effective_model_role_assignments_for_episode(
            project_id, episode_id
        )
        if errors:
            raise ValueError("; ".join(errors))
        assignment = assignments.resolve(
            model_roles.ModelRole.HOST_GENERATION
        ) or assignments.resolve(model_roles.ModelRole.EPISODE_PLANNING)
        registry = composition.provider_controller.llm_registry
        if assignment is not None:
            return cast(LLMProvider, registry.get(assignment.provider)), assignment.model
        provider_ids = registry.provider_ids()
        if not provider_ids:
            raise RuntimeError("no configured LLM provider is available for transcript repair")
        provider = cast(LLMProvider, registry.get(provider_ids[0]))
        models = provider.models()
        return provider, None if not models else models[0].model

    def _invalidate_episode_audio(self, app: DeeperDiveApp, turn_ids: tuple[str, ...]) -> bool:
        database = self._database(app)
        episode_id = self._episode_id(app)
        removed = False
        with database.transaction() as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tts_artifacts'"
            ).fetchone()
            if table is not None:
                for turn_id in turn_ids:
                    cursor = connection.execute("DELETE FROM tts_artifacts WHERE turn_id=?", (turn_id,))
                    removed = removed or cursor.rowcount > 0
            timeline_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audio_timelines'"
            ).fetchone()
            if timeline_table is not None:
                cursor = connection.execute(
                    "DELETE FROM audio_timelines WHERE episode_id=?", (episode_id,)
                )
                removed = removed or cursor.rowcount > 0
        output = app.service.workspaces.project_root(self._project_id(app)) / "output"
        for suffix in (".mp3", ".wav"):
            candidate = output / f"{episode_id}{suffix}"
            if candidate.exists():
                removed = True
            with contextlib.suppress(FileNotFoundError):
                candidate.unlink()
        return removed

    def _regenerate_episode_audio_if_required(self, app: DeeperDiveApp, had_audio: bool) -> None:
        if not had_audio:
            return
        composition = getattr(app.service, "_production_composition", None)
        if composition is None:
            return
        project_id = self._project_id(app)
        episode_id = self._episode_id(app)
        _tts_stage(app.service, project_id, PipelineContext("transcript-repair", episode_id, "tts"))
        _composition_stage(
            app.service,
            project_id,
            PipelineContext("transcript-repair", episode_id, "composition"),
        )

    def _database(self, app: DeeperDiveApp) -> Database:
        root = app.service.workspaces.project_root(self._project_id(app))
        return Database(root / "project.db")

    @staticmethod
    def _turn_from_row(row: object) -> TranscriptTurn:
        return TranscriptTurn(
            id=str(row["id"]),
            segment_ordinal=int(row["segment_ordinal"]),
            turn_ordinal=int(row["turn_ordinal"]),
            speaker_id=str(row["speaker_id"]),
            speaker_name=str(row["speaker_name"]),
            text=str(row["text"]),
            evidence_ids=tuple(str(item) for item in json.loads(str(row["evidence_ids_json"]))),
        )

    @classmethod
    def _claim_from_row(cls, row: object) -> TurnClaimSummary:
        return TurnClaimSummary(
            id=str(row["id"]),
            text=str(row["text"]),
            state="unverified" if row["state"] is None else str(row["state"]),
            rationale="" if row["rationale"] is None else str(row["rationale"]),
            supporting_ids=cls._json_ids(row["supporting_evidence_ids_json"]),
            contradicting_ids=cls._json_ids(row["contradicting_evidence_ids_json"]),
        )

    @staticmethod
    def _json_ids(value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        return tuple(str(item) for item in json.loads(str(value)))

    @staticmethod
    def _optional_text(value: object) -> str | None:
        return None if value is None else str(value)

    @staticmethod
    def _project_id(app: DeeperDiveApp) -> str:
        if app.current_project_id is None:
            raise RuntimeError("no project open")
        return app.current_project_id

    @staticmethod
    def _episode_id(app: DeeperDiveApp) -> str:
        if app.current_episode_id is None:
            raise RuntimeError("no episode selected")
        return app.current_episode_id


class TranscriptReviewScreen(Screen[None]):
    """Review transcript turns, cited evidence, claims, and export actions."""

    BINDINGS = [
        Binding("enter", "select_turn", "Select turn"),
        Binding("space", "play_selected", "Play selected"),
        Binding("p", "pause_playback", "Pause playback"),
        Binding("c", "claim_inspector", "Claim inspector"),
        Binding("r", "regenerate_turn", "Regenerate turn"),
        Binding("e", "export", "Export"),
    ]

    def __init__(self, controller: TranscriptReviewController | None = None) -> None:
        super().__init__(id="screen-review")
        self.controller = controller or TranscriptReviewController()
        self.turns: tuple[TranscriptTurn, ...] = ()
        self.selected_index = 0

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
            yield Label("Transcript Review", id="screen-title")
            yield Static("", id="chapter-list")
            yield Input(value="1", placeholder="Turn number", id="turn-number")
            yield Button("Select Turn", name="select-turn")
            yield Static("", id="transcript-turn")
            yield Static("", id="turn-citations")
            yield Static("", id="claims-pane")
            yield Static("", id="source-passages")
            yield Button("Play Selected Turn", name="play-selected-turn")
            yield Button("Pause Playback", name="pause-playback")
            yield Button("Resume Playback", name="resume-playback")
            yield Static("", id="playback-status")
            yield Button("Open Claim Inspector", name="claim-inspector")
            yield Button("Regenerate Turn / Section", name="regenerate-turn")
            yield Button("Export", name="export-review")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_review()
        self.query_one("#playback-status", Static).update(self._playback_strategy_text())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        actions = {
            "select-turn": self.action_select_turn,
            "play-selected-turn": self.action_play_selected,
            "pause-playback": self.action_pause_playback,
            "resume-playback": self.action_resume_playback,
            "claim-inspector": self.action_claim_inspector,
            "regenerate-turn": self.action_regenerate_turn,
            "export-review": self.action_export,
        }
        action = actions.get(name)
        if action is not None:
            action()
        elif name:
            self._app.action_navigate(name)

    def refresh_review(self, status: str = "Ready") -> None:
        try:
            self.turns = self.controller.turns(self._app)
        except RuntimeError as exc:
            self.turns = ()
            self.query_one("#chapter-list", Static).update(str(exc))
            self._status(str(exc))
            return
        if not self.turns:
            self.query_one("#chapter-list", Static).update("No transcript turns yet.")
            self.query_one("#transcript-turn", Static).update("")
            self.query_one("#turn-citations", Static).update("")
            self.query_one("#claims-pane", Static).update("")
            self.query_one("#source-passages", Static).update("")
            self._status(status)
            return
        self.selected_index = min(self.selected_index, len(self.turns) - 1)
        self.query_one("#chapter-list", Static).update(self._chapter_text())
        self._render_selected(status)

    def action_select_turn(self) -> None:
        try:
            index = int(self.query_one("#turn-number", Input).value) - 1
        except ValueError:
            self._status("Enter a numeric turn number")
            return
        if not 0 <= index < len(self.turns):
            self._status("Turn number is out of range")
            return
        self.selected_index = index
        self._render_selected("Selected turn")

    def action_play_selected(self) -> None:
        turn = self._selected_turn()
        if turn is None:
            self._status("No turn selected")
            return
        state = self.controller.play_turn(self._app, turn)
        self._render_playback_state(state)

    def action_pause_playback(self) -> None:
        self._render_playback_state(self.controller.pause_playback())

    def action_resume_playback(self) -> None:
        self._render_playback_state(self.controller.resume_playback())

    def action_claim_inspector(self) -> None:
        turn = self._selected_turn()
        if turn is None:
            self._status("No turn selected")
            return
        self.app.push_screen(self.controller.claim_inspector(self._app, turn.id))

    def action_regenerate_turn(self) -> None:
        turn = self._selected_turn()
        if turn is None:
            self._status("No turn selected")
            return
        try:
            self.controller.repair_turn(turn.id, self._app)
        except (KeyError, RuntimeError, ValueError) as exc:
            self._status(str(exc))
            return
        self.refresh_review("Regenerated selected turn/section")

    def action_export(self) -> None:
        try:
            path = self.controller.export_markdown(self._app)
        except RuntimeError as exc:
            self._status(str(exc))
            return
        self._status(f"Exported transcript review: {path}")

    def _playback_strategy_text(self) -> str:
        capabilities = self.controller.playback.capabilities
        return "\n".join(
            (
                f"Playback strategy: {capabilities.strategy}",
                f"Play: {capabilities.can_play} | Pause: {capabilities.can_pause} | "
                f"Seek/skip: {capabilities.can_seek}",
                capabilities.detail,
            )
        )

    def _render_playback_state(self, state: PlaybackState) -> None:
        position = "unknown" if state.position_seconds is None else f"{state.position_seconds:.1f}s"
        self.query_one("#playback-status", Static).update(
            f"{self._playback_strategy_text()}\nLast action: {state.message}\nPosition: {position}"
        )
        self._status(state.message)

    def _chapter_text(self) -> str:
        return "\n".join(self._chapter_row(index, turn) for index, turn in enumerate(self.turns))

    def _chapter_row(self, index: int, turn: TranscriptTurn) -> str:
        selected = "*" if index == self.selected_index else " "
        chapter = turn.segment_ordinal + 1
        ordinal = turn.turn_ordinal + 1
        return f"{selected} {index + 1}. Chapter {chapter} Turn {ordinal} — {turn.speaker_name}"

    def _render_selected(self, status: str) -> None:
        turn = self._selected_turn()
        if turn is None:
            self._status("No turn selected")
            return
        self.query_one("#turn-number", Input).value = str(self.selected_index + 1)
        self.query_one("#transcript-turn", Static).update(
            f"{turn.speaker_name} [{turn.id}]\n{turn.text}"
        )
        self.query_one("#turn-citations", Static).update(self._citation_text(turn))
        claims = self.controller.claims(self._app, turn.id)
        evidence_ids = self._evidence_ids(turn, claims)
        self.query_one("#claims-pane", Static).update(self._claims_text(claims))
        passages = self.controller.passages(self._app, evidence_ids)
        self.query_one("#source-passages", Static).update(self._passages_text(passages))
        self.query_one("#chapter-list", Static).update(self._chapter_text())
        self._status(status)

    @staticmethod
    def _citation_text(turn: TranscriptTurn) -> str:
        values = ", ".join(turn.evidence_ids) if turn.evidence_ids else "none"
        return f"Citations: {values}"

    @staticmethod
    def _claims_text(claims: tuple[TurnClaimSummary, ...]) -> str:
        rows = [f"[{claim.state}] {claim.text}\n  {claim.rationale}".rstrip() for claim in claims]
        return "\n".join(rows) if rows else "No claims for selected turn."

    @staticmethod
    def _evidence_ids(
        turn: TranscriptTurn, claims: tuple[TurnClaimSummary, ...]
    ) -> tuple[str, ...]:
        evidence_ids: list[str] = list(turn.evidence_ids)
        for claim in claims:
            evidence_ids.extend(claim.supporting_ids)
            evidence_ids.extend(claim.contradicting_ids)
        return tuple(dict.fromkeys(evidence_ids))

    @staticmethod
    def _passages_text(passages: tuple[SourcePassageSummary, ...]) -> str:
        rows = []
        for item in passages:
            location = item.location or "location unavailable"
            rows.append(
                f"[{item.chunk_id}] {item.origin} | {item.source_title} | {location}\n{item.text}"
            )
        return "\n\n".join(rows) if rows else "No source passages for selected turn."

    def _selected_turn(self) -> TranscriptTurn | None:
        return None if not self.turns else self.turns[self.selected_index]

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
