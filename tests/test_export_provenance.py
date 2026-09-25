from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.repositories import CorpusRepository, SourceChunkRecord, SourceRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager


def test_episode_export_preserves_transcript_source_and_claim_provenance(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 25, 13, 0, 0, tzinfo=UTC)),
    )
    project = service.create_project("Export provenance")
    timestamp = format_timestamp(service.clock.now())
    source = SourceRecord(
        id="source-1",
        project_id=project.id,
        origin="user",
        source_type="text",
        title="Primary Source",
        imported_at=timestamp,
        locator="fixture.md",
        status="ready",
    )
    chunk = SourceChunkRecord(
        id="chunk-1",
        source_id=source.id,
        ordinal=0,
        text="Exact source passage used by the generated turn.",
        content_hash="hash",
        location="chapter 2 / paragraph 4",
    )
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_source(source)
    corpus.create_chunk(chunk)
    host = create_host_from_preset("curious_explainer", project.id)
    repository = service.hosts(project.id)
    repository.create_host(host.to_record())
    episode = EpisodeRecord(
        id="episode-1",
        project_id=project.id,
        title="Provenance episode",
        created_at=timestamp,
        modified_at=timestamp,
    )
    repository.create_episode(episode, [host.id])
    run = GenerationRunRecord(
        id="run-1",
        episode_id=episode.id,
        stage="export",
        state="completed",
        created_at=timestamp,
        modified_at=timestamp,
    )
    service.runs(project.id).create(run)
    HostTurnService(database)
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                "turn-1",
                episode.id,
                2,
                3,
                host.id,
                "Generated turn cites the source passage.",
                json.dumps((chunk.id,)),
            ),
        )
        connection.execute(
            """CREATE TABLE material_claims(
                id TEXT PRIMARY KEY,
                turn_id TEXT NOT NULL,
                text TEXT NOT NULL,
                span_start INTEGER NOT NULL DEFAULT 0
            )"""
        )
        connection.execute(
            """CREATE TABLE claim_verifications(
                claim_id TEXT PRIMARY KEY,
                state TEXT,
                rationale TEXT,
                confidence REAL,
                supporting_evidence_ids_json TEXT,
                contradicting_evidence_ids_json TEXT
            )"""
        )
        connection.execute(
            """INSERT INTO material_claims(id,turn_id,text,span_start)
            VALUES (?,?,?,?)""",
            ("claim-1", "turn-1", "The generated turn makes a checkable claim.", 0),
        )
        connection.execute(
            """INSERT INTO claim_verifications(
                claim_id,state,rationale,confidence,supporting_evidence_ids_json,
                contradicting_evidence_ids_json
            ) VALUES (?,?,?,?,?,?)""",
            (
                "claim-1",
                "supported",
                "The source passage supports the claim.",
                0.9,
                json.dumps((chunk.id,)),
                json.dumps(()),
            ),
        )

    export = EpisodeLibraryExportService(service.workspaces).export(
        project.id,
        episode,
        run,
        output_dir=tmp_path / "exports",
    )

    transcript = export.transcript.read_text(encoding="utf-8")
    assert "Chapter 3 / Turn 4" in transcript
    assert f"Speaker ID: {host.id}" in transcript
    assert "Citations: chunk-1" in transcript
    assert "Claim ID: claim-1" in transcript
    assert "supports claim claim-1" in transcript
    assert "Primary Source" in transcript
    assert "chapter 2 / paragraph 4" in transcript
    assert "Exact source passage used by the generated turn." in transcript

    metadata = json.loads(export.metadata.read_text(encoding="utf-8"))
    assert metadata["episode_id"] == episode.id
    assert metadata["project_id"] == project.id
    assert metadata["run_id"] == run.id
