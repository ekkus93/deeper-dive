from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App
from textual.widgets import Static

from deeper_dive.claim_inspector_screen import ClaimInspectorController, ClaimInspectorScreen
from deeper_dive.claim_verification import ClaimVerificationService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.material_claims import MaterialClaimService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodeRecord,
    HostEpisodeRepository,
    HostProfileRecord,
)
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)


class Unused:
    def generate_turn(self, decision: object) -> dict[str, object]:
        raise AssertionError("unused")

    def classify(self, request: dict[str, object]) -> dict[str, object]:
        raise AssertionError("unused")


class InspectorApp(App[None]):
    def __init__(self, screen: ClaimInspectorScreen) -> None:
        super().__init__()
        self.inspector = screen

    def on_mount(self) -> None:
        self.push_screen(self.inspector)


def test_claim_inspector_traces_claim_to_exact_source_chunks_and_repairs(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    database.initialize()
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p", "Inspect", "t", "t"))
    corpus.create_source(SourceRecord("s1", "p", "user", "text", "Primary", "t", status="ready"))
    corpus.create_source(
        SourceRecord("s2", "p", "supplemental", "text", "Web", "t", status="ready")
    )
    corpus.create_chunk(SourceChunkRecord("good", "s1", 0, "The figure is 12.", "h1", "page 4"))
    corpus.create_chunk(
        SourceChunkRecord("bad", "s2", 0, "The figure is not 10.", "h2", "section 2")
    )
    episodes = HostEpisodeRepository(database)
    episodes.create_host(HostProfileRecord("h", "p", "Host"))
    episodes.create_episode(EpisodeRecord("e", "p", "Episode", "t", "t"), ["h"])
    HostTurnService(database, Unused())
    MaterialClaimService(database)
    ClaimVerificationService(database, Unused())
    with database.transaction() as db:
        db.execute(
            "INSERT INTO conversation_turns VALUES (?,?,?,?,?,?,?)",
            ("turn", "e", 0, 0, "h", "The figure is 10.", "[]"),
        )
        db.execute(
            "INSERT INTO material_claims VALUES (?,?,?,?,?,?,?,?)",
            ("claim", "p", "e", "turn", "The figure is 10.", 0, 17, "t"),
        )
        db.execute(
            "INSERT INTO claim_verifications VALUES (?,?,?,?,?,?)",
            ("claim", "contradicted", "Primary evidence differs.", 0.9, '["good"]', '["bad"]'),
        )
    repaired: list[str] = []
    controller = ClaimInspectorController(database, repaired.append)
    screen = ClaimInspectorScreen(controller, "turn")
    app = InspectorApp(screen)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        details = str(screen.query_one("#claim-details", Static).render())
        evidence = str(screen.query_one("#claim-evidence", Static).render())
        passage = str(screen.query_one("#source-passage", Static).render())
        assert "contradicted" in details
        assert "user | Primary | page 4" in evidence
        assert "supplemental | Web | section 2" in evidence
        assert "The figure is 12." in passage
        assert "The figure is not 10." in passage
        screen.action_repair()
        assert repaired == ["turn"]
