"""Transcript and review TUI with claims and evidence navigation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.claim_inspector_screen import ClaimInspectorController, ClaimInspectorScreen
from deeper_dive.storage.database import Database

if TYPE_CHECKING:
    from deeper_dive.tui import DeeperDiveApp


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


class TranscriptReviewController:
    """Read transcript, claim, and source-passage state for review screens."""

    def __init__(self, repair: callable | None = None) -> None:
        self.repair_callback = repair

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
        import json

        return tuple(
            TranscriptTurn(
                str(row["id"]),
                int(row["segment_ordinal"]),
                int(row["turn_ordinal"]),
                str(row["speaker_id"]),
                str(row["speaker_name"]),
                str(row["text"]),
                tuple(str(item) for item in json.loads(str(row["evidence_ids_json"]))),
            )
            for row in rows
        )

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
        import json

        return tuple(
            TurnClaimSummary(
                str(row["id"]),
                str(row["text"]),
                "unverified" if row["state"] is None else str(row["state"]),
                "" if row["rationale"] is None else str(row["rationale"]),
                ()
                if row["supporting_evidence_ids_json"] is None
                else tuple(json.loads(str(row["supporting_evidence_ids_json"]))),
                ()
                if row["contradicting_evidence_ids_json"] is None
                else tuple(json.loads(str(row["contradicting_evidence_ids_json"]))),
            )
            for row in rows
        )

    def passages(self, app: DeeperDiveApp, chunk_ids: tuple[str, ...]) -> tuple[SourcePassageSummary, ...]:
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
                chunk_id,
                str(by_id[chunk_id]["title"]),
                str(by_id[chunk_id]["origin"]),
                None if by_id[chunk_id]["location"] is None else str(by_id[chunk_id]["location"]),
                str(by_id[chunk_id]["text"]),
            )
            for chunk_id in chunk_ids
            if chunk_id in by_id
        )

    def repair_turn(self, turn_id: str) -> None:
        if self.repair_callback is None:
            raise RuntimeError("targeted transcript repair is not configured")
        self.repair_callback(turn_id)

    def export_markdown(self, app: DeeperDiveApp) -> Path:
        project_id = self._project_id(app)
        episode_id = self._episode_id(app)
        path = app.service.workspaces.project_root(project_id) / "output" / f"{episode_id}-transcript-review.md"
        turns = self.turns(app)
        lines = [f"# Transcript review: {episode_id}", ""]
        for turn in turns:
            lines.extend(
                (
                    f"## Chapter {turn.segment_ordinal + 1} / Turn {turn.turn_ordinal + 1}: {turn.speaker_name}",
                    "",
                    turn.text,
                    "",
                )
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def claim_inspector(self, app: DeeperDiveApp, turn_id: str) -> ClaimInspectorScreen:
        return ClaimInspectorScreen(
            ClaimInspectorController(self._database(app), self.repair_callback), turn_id
        )

    def _database(self, app: DeeperDiveApp) -> Database:
        project_id = self._project_id(app)
        return Database(app.service.workspaces.project_root(project_id) / "project.db")

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
        Binding("c", "claim_inspector", "Claim inspector"),
        Binding("r", "regenerate_turn", "Regenerate turn"),
        Binding("e", "export", "Export"),
    ]

    def __init__(self) -> None:
        super().__init__(id="screen-review")
        self.turns: tuple[TranscriptTurn, ...] = ()
        self.selected_index = 0

    @property
    def _app(self) -> DeeperDiveApp:
        return cast("DeeperDiveApp", self.app)

    @property
    def _controller(self) -> TranscriptReviewController:
        return self._app.transcript_review_controller

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
            yield Button("Open Claim Inspector", name="claim-inspector")
            yield Button("Regenerate Turn / Section", name="regenerate-turn")
            yield Button("Export", name="export-review")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_review()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        actions = {
            "select-turn": self.action_select_turn,
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
            self.turns = self._controller.turns(self._app)
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

    def action_claim_inspector(self) -> None:
        turn = self._selected_turn()
        if turn is None:
            self._status("No turn selected")
            return
        self.app.push_screen(self._controller.claim_inspector(self._app, turn.id))

    def action_regenerate_turn(self) -> None:
        turn = self._selected_turn()
        if turn is None:
            self._status("No turn selected")
            return
        try:
            self._controller.repair_turn(turn.id)
        except RuntimeError as exc:
            self._status(str(exc))
            return
        self.refresh_review("Regenerated selected turn/section")

    def action_export(self) -> None:
        try:
            path = self._controller.export_markdown(self._app)
        except RuntimeError as exc:
            self._status(str(exc))
            return
        self._status(f"Exported transcript review: {path}")

    def _chapter_text(self) -> str:
        rows = []
        for index, turn in enumerate(self.turns):
            selected = "*" if index == self.selected_index else " "
            rows.append(
                f"{selected} {index + 1}. Chapter {turn.segment_ordinal + 1} "
                f"Turn {turn.turn_ordinal + 1} — {turn.speaker_name}"
            )
        return "\n".join(rows)

    def _render_selected(self, status: str) -> None:
        turn = self._selected_turn()
        if turn is None:
            self._status("No turn selected")
            return
        self.query_one("#turn-number", Input).value = str(self.selected_index + 1)
        self.query_one("#transcript-turn", Static).update(
            f"{turn.speaker_name} [{turn.id}]\n{turn.text}"
        )
        self.query_one("#turn-citations", Static).update(
            "Citations: " + (", ".join(turn.evidence_ids) if turn.evidence_ids else "none")
        )
        claims = self._controller.claims(self._app, turn.id)
        claim_lines = []
        evidence_ids: list[str] = list(turn.evidence_ids)
        for claim in claims:
            claim_lines.append(f"[{claim.state}] {claim.text}\n  {claim.rationale}".rstrip())
            evidence_ids.extend(claim.supporting_ids)
            evidence_ids.extend(claim.contradicting_ids)
        self.query_one("#claims-pane", Static).update(
            "\n".join(claim_lines) if claim_lines else "No claims for selected turn."
        )
        passages = self._controller.passages(self._app, tuple(dict.fromkeys(evidence_ids)))
        self.query_one("#source-passages", Static).update(
            "\n\n".join(
                f"[{item.chunk_id}] {item.origin} | {item.source_title} | "
                f"{item.location or 'location unavailable'}\n{item.text}"
                for item in passages
            )
            or "No source passages for selected turn."
        )
        self.query_one("#chapter-list", Static).update(self._chapter_text())
        self._status(status)

    def _selected_turn(self) -> TranscriptTurn | None:
        if not self.turns:
            return None
        return self.turns[self.selected_index]

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
