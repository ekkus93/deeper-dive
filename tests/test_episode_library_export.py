from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tui import DeeperDiveApp


def test_library_export_writes_selected_episode_artifacts(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Export")
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episode = EpisodeConfigurationService(database, clock=service.clock).create(
        project.id, EpisodeConfiguration(title="Export me")
    )
    _seed_transcript(database, episode.id, "selected episode transcript")
    timestamp = format_timestamp(service.clock.now())
    run = GenerationRunRecord(
        id=str(new_run_id()),
        episode_id=episode.id,
        stage="export",
        state="completed",
        created_at=timestamp,
        modified_at=timestamp,
    )
    service.runs(project.id).create(run)
    output = service.workspaces.project_root(project.id) / "output"
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{episode.id}.wav").write_bytes(b"selected-audio")

    app = DeeperDiveApp(service)
    app.current_project_id = project.id
    item = EpisodeLibraryController.items(app)[0]
    result = EpisodeLibraryController.export(app, item)

    assert all(path.is_file() for path in result.paths)
    assert "selected episode transcript" in result.transcript.read_text(encoding="utf-8")
    metadata = json.loads(result.metadata.read_text(encoding="utf-8"))
    assert metadata["episode_id"] == episode.id
    assert metadata["run_id"] == run.id
    assert result.audio is not None
    assert result.audio.read_bytes() == b"selected-audio"
    assert episode.id in result.transcript.name


def test_library_export_rejects_incomplete_episode(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Incomplete")
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episode = EpisodeConfigurationService(database, clock=service.clock).create(
        project.id, EpisodeConfiguration(title="Not ready")
    )
    timestamp = format_timestamp(service.clock.now())
    service.runs(project.id).create(
        GenerationRunRecord(
            id=str(new_run_id()),
            episode_id=episode.id,
            stage="conversation",
            state="paused",
            created_at=timestamp,
            modified_at=timestamp,
        )
    )
    app = DeeperDiveApp(service)
    app.current_project_id = project.id

    with pytest.raises(ValueError, match="paused.*not exportable"):
        EpisodeLibraryController.export(app, EpisodeLibraryController.items(app)[0])


def _seed_transcript(database: Database, episode_id: str, text: str) -> None:
    with database.transaction() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS conversation_turns (
            id TEXT PRIMARY KEY, episode_id TEXT NOT NULL, segment_ordinal INTEGER NOT NULL,
            turn_ordinal INTEGER NOT NULL, speaker_id TEXT NOT NULL, text TEXT NOT NULL,
            evidence_ids_json TEXT NOT NULL DEFAULT '[]')"""
        )
        connection.execute(
            """INSERT INTO conversation_turns(
            id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            (f"turn-{episode_id}", episode_id, 0, 0, "host-1", text, "[]"),
        )


def _service(tmp_path: Path) -> DeeperDiveService:
    return DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)),
    )


def test_review_and_real_exports_stay_isolated_across_two_episodes(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Two episode isolation")
    root = service.workspaces.project_root(project.id)
    database = Database(root / "project.db")
    config_service = EpisodeConfigurationService(database, clock=service.clock)
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    cases: list[tuple[str, str, str, bytes]] = []
    timestamp = format_timestamp(service.clock.now())

    for title, text, audio in (
        ("First", "First episode unique transcript", b"first-episode-audio"),
        ("Second", "Second episode unique transcript", b"second-episode-audio"),
    ):
        episode = config_service.create(project.id, EpisodeConfiguration(title=title))
        _seed_transcript(database, episode.id, text)
        run = GenerationRunRecord(
            id=str(new_run_id()),
            episode_id=episode.id,
            stage="export",
            state="completed",
            created_at=timestamp,
            modified_at=timestamp,
        )
        service.runs(project.id).create(run)
        (output / f"{episode.id}.wav").write_bytes(audio)
        cases.append((episode.id, run.id, text, audio))

    app = DeeperDiveApp(service)
    app.current_project_id = project.id
    assert cases[0][0] != cases[1][0]
    exported_paths: list[Path] = []
    for episode_id, run_id, text, audio in cases:
        app.current_episode_id = episode_id
        app.current_run_id = run_id
        turns = TranscriptReviewController().turns(app)
        assert [turn.text for turn in turns] == [text]
        selected = next(
            item for item in EpisodeLibraryController.items(app) if item.episode.id == episode_id
        )
        assert selected.run is not None and selected.run.id == run_id
        exported = EpisodeLibraryController.export(app, selected)
        exported_paths.extend(exported.paths)
        assert text in exported.transcript.read_text(encoding="utf-8")
        metadata = json.loads(exported.metadata.read_text(encoding="utf-8"))
        assert metadata["episode_id"] == episode_id
        assert metadata["run_id"] == run_id
        assert exported.audio is not None
        assert exported.audio.read_bytes() == audio
        assert all(path.is_file() for path in exported.paths)
    assert len(set(exported_paths)) == len(exported_paths)
