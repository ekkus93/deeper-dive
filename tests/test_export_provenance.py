from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager


def test_episode_export_preserves_turn_source_passage_provenance(tmp_path: Path) -> None:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)),
    )
    project = service.create_project("Provenance export")
    source = service.add_pasted_source(
        project.id,
        "Chapter 1 Source",
        "A cited source passage about durable provider-backed provenance.",
    )
    chunk = service.list_source_chunks(project.id, source.id)[0]
    host = create_host_from_preset("curious_explainer", project.id)
    service.hosts(project.id).create_host(host.to_record())
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episode = EpisodeConfigurationService(database).create(
        project.id,
        EpisodeConfiguration(
            title="Provenance Episode",
            focus="Preserve source passages",
            host_ids=(host.id,),
        ),
    )
    timestamp = format_timestamp(service.clock.now())
    run = GenerationRunRecord(
        id="provenance-run",
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
                "turn-with-provenance",
                episode.id,
                0,
                0,
                host.id,
                "The generated turn cites a concrete source passage.",
                json.dumps([chunk.id]),
            ),
        )
        connection.execute(
            """INSERT INTO conversation_turn_provider_identity(
                turn_id,provider_id,model
            ) VALUES (?,?,?)""",
            ("turn-with-provenance", "planner", "fake-v1"),
        )

    result = EpisodeLibraryExportService(service.workspaces).export(
        project.id,
        episode,
        run,
        output_dir=tmp_path / "exports",
    )

    transcript = result.transcript.read_text(encoding="utf-8")
    metadata = json.loads(result.metadata.read_text(encoding="utf-8"))

    assert "segment 1" in transcript
    assert "turn 1" in transcript
    assert host.id in transcript
    assert chunk.id in transcript
    assert "Chapter 1 Source" in transcript
    assert chunk.text in transcript
    assert metadata == {
        "episode_id": episode.id,
        "project_id": project.id,
        "run_id": run.id,
        "run_state": "completed",
        "title": episode.title,
    }
