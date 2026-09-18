"""Claim verification inspector with exact evidence provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class ClaimInspection:
    claim_id: str
    turn_id: str
    text: str
    state: str
    rationale: str
    confidence: float | None
    supporting_ids: tuple[str, ...]
    contradicting_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidencePassage:
    chunk_id: str
    source_id: str
    source_title: str
    origin: str
    location: str | None
    text: str


class ClaimInspectorController:
    """Read persisted claims/verifications and resolve cited chunks to source passages."""

    def __init__(
        self,
        database: Database,
        repair: Callable[[str], object] | None = None,
    ) -> None:
        self.database = database
        self.repair_callback = repair

    def claims_for_turn(self, turn_id: str) -> list[ClaimInspection]:
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT mc.id,mc.turn_id,mc.text,cv.state,cv.rationale,cv.confidence,
                cv.supporting_evidence_ids_json,cv.contradicting_evidence_ids_json
                FROM material_claims mc LEFT JOIN claim_verifications cv ON cv.claim_id=mc.id
                WHERE mc.turn_id=? ORDER BY mc.span_start,mc.id""",
                (turn_id,),
            ).fetchall()
        return [
            ClaimInspection(
                str(row["id"]),
                str(row["turn_id"]),
                str(row["text"]),
                "unverified" if row["state"] is None else str(row["state"]),
                "" if row["rationale"] is None else str(row["rationale"]),
                None if row["confidence"] is None else float(row["confidence"]),
                self._ids(row["supporting_evidence_ids_json"]),
                self._ids(row["contradicting_evidence_ids_json"]),
            )
            for row in rows
        ]

    def evidence(self, claim: ClaimInspection) -> list[EvidencePassage]:
        ids = tuple(dict.fromkeys((*claim.supporting_ids, *claim.contradicting_ids)))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.database.connection() as db:
            rows = db.execute(
                f"""SELECT c.id,c.source_id,c.text,c.location,s.title,s.origin
                FROM source_chunks c JOIN sources s ON s.id=c.source_id
                WHERE c.id IN ({placeholders})""",
                ids,
            ).fetchall()
        by_id = {str(row["id"]): row for row in rows}
        return [
            EvidencePassage(
                chunk_id,
                str(by_id[chunk_id]["source_id"]),
                str(by_id[chunk_id]["title"]),
                str(by_id[chunk_id]["origin"]),
                None if by_id[chunk_id]["location"] is None else str(by_id[chunk_id]["location"]),
                str(by_id[chunk_id]["text"]),
            )
            for chunk_id in ids
            if chunk_id in by_id
        ]

    def repair(self, turn_id: str) -> None:
        if self.repair_callback is None:
            raise RuntimeError("targeted repair is not configured")
        self.repair_callback(turn_id)

    @staticmethod
    def _ids(value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        return tuple(str(item) for item in json.loads(str(value)))


class ClaimInspectorScreen(Screen[None]):
    BINDINGS = [Binding("ctrl+r", "repair", "Repair turn")]

    def __init__(self, controller: ClaimInspectorController, turn_id: str) -> None:
        super().__init__(id="screen-claim-inspector")
        self.controller = controller
        self.turn_id = turn_id
        self.claims: list[ClaimInspection] = []
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Claim Inspector", id="screen-title")
        yield Input(placeholder="Claim number", id="claim-number", value="1")
        yield Button("Select Claim", id="action-select-claim", name="select-claim")
        yield Static("", id="claim-details")
        yield Static("", id="claim-evidence")
        yield Static("", id="source-passage")
        yield Button("Regenerate / Repair Turn", id="action-repair", name="repair")
        yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_claims()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.name == "select-claim":
            self.action_select_claim()
        elif event.button.name == "repair":
            self.action_repair()

    def refresh_claims(self) -> None:
        self.claims = self.controller.claims_for_turn(self.turn_id)
        if not self.claims:
            self.query_one("#claim-details", Static).update("No material claims for this turn.")
            self.query_one("#claim-evidence", Static).update("")
            self.query_one("#source-passage", Static).update("")
            return
        self.selected_index = min(self.selected_index, len(self.claims) - 1)
        self._render_selected()

    def action_select_claim(self) -> None:
        try:
            index = int(self.query_one("#claim-number", Input).value) - 1
        except ValueError:
            self._status("Enter a numeric claim number")
            return
        if not 0 <= index < len(self.claims):
            self._status("Claim number is out of range")
            return
        self.selected_index = index
        self._render_selected()

    def action_repair(self) -> None:
        if not self.claims:
            self._status("No claim selected")
            return
        self.controller.repair(self.claims[self.selected_index].turn_id)
        self.refresh_claims()
        self._status("Turn repaired and claim inspection refreshed")

    def _render_selected(self) -> None:
        claim = self.claims[self.selected_index]
        confidence = "n/a" if claim.confidence is None else f"{claim.confidence:.2f}"
        self.query_one("#claim-details", Static).update(
            f"Claim {self.selected_index + 1}/{len(self.claims)}: {claim.text}\n"
            f"State: {claim.state} | Confidence: {confidence}\nRationale: {claim.rationale}"
        )
        evidence = self.controller.evidence(claim)
        relations = []
        passages = []
        for item in evidence:
            relation = "supports" if item.chunk_id in claim.supporting_ids else "contradicts"
            location = item.location or "location unavailable"
            relations.append(
                f"[{item.chunk_id}] {relation} | {item.origin} | {item.source_title} | {location}"
            )
            passages.append(f"[{item.chunk_id}] {item.text}")
        self.query_one("#claim-evidence", Static).update("\n".join(relations) or "No cited evidence")
        self.query_one("#source-passage", Static).update("\n\n".join(passages))

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
