"""Guided Library transcript repair remains wired to production after restart."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.claim_verification import ClaimVerificationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.material_claims import ExtractedClaim, MaterialClaimService
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.user_config import UserConfigStore


class _SelectedTurnExtractor:
    """Select the actual generated turn, not an artificially seeded turn."""

    def extract(self, text: str) -> list[ExtractedClaim]:
        return [ExtractedClaim(text, 0, len(text))]


class _NeedsRepairVerifier:
    def classify(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "state": "insufficient_evidence",
            "rationale": "Deterministic acceptance requires factual repair.",
            "supporting_evidence_ids": [],
            "contradicting_evidence_ids": [],
        }


def test_restarted_guided_library_repairs_generated_turn_through_production(
    completed_episode_acceptance: Callable[..., Any],
) -> None:
    """Repair must update only the selected durable turn and rebuild its audio."""
    completed = completed_episode_acceptance()
    service = DeeperDiveService(WorkspaceManager(completed.service.workspaces.data_dir))
    app = GuidedDeeperDiveApp(service)
    app.current_project_id = completed.project_id
    app.current_episode_id = completed.episode_id
    app.current_run_id = completed.run_id
    before = TranscriptReviewController().turns(app)
    assert len(before) >= 2
    selected = before[0]

    database = app.composition.database_for_project(completed.project_id)
    # Use real extraction and verification services to put a generated turn in
    # a durable repair-worthy state; no conversation/artifact repository seeding.
    claims = MaterialClaimService(database, _SelectedTurnExtractor()).extract_turn(
        completed.project_id,
        selected,
    )
    assert len(claims) == 1
    result = ClaimVerificationService(database, _NeedsRepairVerifier()).verify(claims[0], [])
    assert result.state == "insufficient_evidence"

    async def verify_repair() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            app.current_project_id = completed.project_id
            app.current_episode_id = completed.episode_id
            app.current_run_id = completed.run_id
            app.action_navigate("library")
            await pilot.pause()
            library = app.screen
            assert library.selected_episode_id == completed.episode_id
            library.action_open_selected()
            await pilot.pause()
            review = app.screen
            assert review.id == "screen-review"
            assert review.turns[0].id == selected.id
            review.action_regenerate_turn()
            await pilot.pause()
            assert "Regenerated selected turn/section" in str(
                review.query_one("#screen-status", Static).render()
            )
            assert review.turns[0].id == selected.id
            assert review.turns[0].text != selected.text
            assert tuple(turn.id for turn in review.turns) == completed.turn_ids
            assert [(turn.id, turn.text) for turn in review.turns[1:]] == [
                (turn.id, turn.text) for turn in before[1:]
            ]

    asyncio.run(verify_repair())
    assert AudioTimelineRepository(database).get(completed.episode_id) is not None
    audio = service.workspaces.project_root(completed.project_id) / "output"
    assert (audio / f"{completed.episode_id}.wav").is_file()
    assert UserConfigStore(service.workspaces.data_dir / "config.json").load().defaults[
        "host_generation"
    ] == "fake:fake-v1"
