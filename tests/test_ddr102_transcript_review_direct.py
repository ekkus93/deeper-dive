from __future__ import annotations

from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository, HostProfileRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import (
    SourcePassageSummary,
    TranscriptReviewController,
    TranscriptReviewScreen,
    TranscriptTurn,
    TurnClaimSummary,
)
from deeper_dive.tui import DeeperDiveApp


def _review_app(tmp_path: Path) -> tuple[DeeperDiveApp, str]:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("DDR-102 direct review")
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    repository = HostEpisodeRepository(database)
    repository.create_host(HostProfileRecord("host-1", project.id, "Reviewer"))
    episode = EpisodeConfigurationService(database).create(
        project.id,
        EpisodeConfiguration(title="Review episode", host_ids=("host-1",)),
    )
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                "turn-1",
                episode.id,
                0,
                0,
                "host-1",
                "Durable review text",
                '["chunk-1"]',
            ),
        )
    app = DeeperDiveApp(service)
    app.current_project_id = project.id
    app.current_episode_id = episode.id
    return app, episode.id


def test_ddr102_review_renderers_cover_chapters_claims_and_citations() -> None:
    turn = TranscriptTurn("turn-1", 0, 0, "host-1", "Reviewer", "Text", ("chunk-1",))
    claim = TurnClaimSummary(
        "claim-1",
        "Material claim",
        "supported",
        "Evidence agrees",
        ("chunk-1",),
        (),
    )
    passage = SourcePassageSummary(
        "chunk-1",
        "Source title",
        "user",
        "page 1",
        "Evidence passage",
    )
    screen = TranscriptReviewScreen()
    screen.turns = (turn,)

    assert "Chapter 1 Turn 1" in screen._chapter_text()
    assert screen._citation_text(turn) == "Citations: chunk-1"
    assert "[supported] Material claim" in screen._claims_text((claim,))
    rendered_passage = screen._passages_text((passage,))
    assert "[chunk-1] user | Source title | page 1" in rendered_passage
    assert "Evidence passage" in rendered_passage


def test_ddr102_review_export_writes_selected_episode_artifact(tmp_path: Path) -> None:
    app, episode_id = _review_app(tmp_path)

    path = TranscriptReviewController().export_markdown(app)

    assert path.is_file()
    assert path.name == f"{episode_id}-transcript-review.md"
    text = path.read_text(encoding="utf-8")
    assert "# Transcript review:" in text
    assert "Chapter 1 / Turn 1: Reviewer" in text
    assert "Durable review text" in text
