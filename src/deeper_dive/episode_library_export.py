"""Episode-specific export workflow shared by library surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeper_dive.export import (
    EpisodeExporter,
    ManifestSource,
    TranscriptCitation,
    TranscriptTurn,
)
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager


@dataclass(frozen=True, slots=True)
class EpisodeExportResult:
    transcript: Path
    manifest: Path
    metadata: Path
    audio: Path | None = None

    @property
    def paths(self) -> tuple[Path, ...]:
        base = (self.transcript, self.manifest, self.metadata)
        return base if self.audio is None else (*base, self.audio)


class EpisodeLibraryExportService:
    """Export durable artifacts for one completed episode."""

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    def export(
        self,
        project_id: str,
        episode: EpisodeRecord,
        run: GenerationRunRecord | None,
        *,
        output_dir: Path | None = None,
    ) -> EpisodeExportResult:
        if episode.project_id != project_id:
            raise ValueError("selected episode does not belong to the open project")
        if run is None:
            raise ValueError("selected episode has no generation run to export")
        if run.episode_id != episode.id:
            raise ValueError("selected generation run does not belong to the episode")
        if run.state != "completed":
            raise ValueError(f"run state {run.state} is not exportable")

        root = self.workspaces.project_root(project_id)
        database = Database(root / "project.db")
        exporter = EpisodeExporter(output_dir or root / "exports")
        stem = exporter.reserve_stem(f"{episode.title}-{episode.id}")
        turns = self._turns(database, episode.id)
        if not turns:
            raise ValueError("completed episode has no transcript turns to export")

        transcript = exporter.write_transcript(stem.with_suffix(".md"), episode.title, turns)
        manifest = exporter.write_manifest(
            stem.with_name(f"{stem.name}-sources.json"), self._sources(database, project_id)
        )
        metadata = exporter.write_metadata(
            stem.with_name(f"{stem.name}-metadata.json"),
            {
                "project_id": project_id,
                "episode_id": episode.id,
                "run_id": run.id,
                "title": episode.title,
                "run_state": run.state,
            },
        )
        audio = self._copy_episode_audio(root, episode.id, stem)
        return EpisodeExportResult(transcript, manifest, metadata, audio)

    @staticmethod
    def _turns(database: Database, episode_id: str) -> tuple[TranscriptTurn, ...]:
        with database.connection() as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_turns'"
            ).fetchone()
            if table is None:
                return ()
            rows = connection.execute(
                """SELECT t.id,t.text,t.speaker_id,t.segment_ordinal,t.turn_ordinal,
                t.evidence_ids_json,COALESCE(h.display_name,t.speaker_id) AS speaker_name
                FROM conversation_turns t LEFT JOIN hosts h ON h.id=t.speaker_id
                WHERE t.episode_id=? ORDER BY t.segment_ordinal,t.turn_ordinal""",
                (episode_id,),
            ).fetchall()
            all_evidence_ids = tuple(
                evidence_id
                for row in rows
                for evidence_id in _evidence_ids(str(row["evidence_ids_json"]))
            )
            citation_map = EpisodeLibraryExportService._citations(connection, all_evidence_ids)
        return tuple(
            TranscriptTurn(
                host=str(row["speaker_name"]),
                text=str(row["text"]),
                speaker_id=str(row["speaker_id"]),
                segment_ordinal=int(row["segment_ordinal"]),
                turn_ordinal=int(row["turn_ordinal"]),
                evidence_ids=_evidence_ids(str(row["evidence_ids_json"])),
                citations=tuple(
                    citation_map[evidence_id]
                    for evidence_id in _evidence_ids(str(row["evidence_ids_json"]))
                    if evidence_id in citation_map
                ),
            )
            for row in rows
        )

    @staticmethod
    def _citations(
        connection: Any,
        evidence_ids: tuple[str, ...],
    ) -> dict[str, TranscriptCitation]:
        ordered_ids = tuple(dict.fromkeys(evidence_ids))
        if not ordered_ids:
            return {}
        placeholders = ",".join("?" for _ in ordered_ids)
        rows = connection.execute(
            f"""SELECT c.id,c.text,c.location,s.title,s.origin,s.locator
            FROM source_chunks c JOIN sources s ON s.id=c.source_id
            WHERE c.id IN ({placeholders})""",
            ordered_ids,
        ).fetchall()
        return {
            str(row["id"]): TranscriptCitation(
                evidence_id=str(row["id"]),
                source_title=str(row["title"]),
                source_origin=str(row["origin"]),
                source_locator=None if row["locator"] is None else str(row["locator"]),
                location=None if row["location"] is None else str(row["location"]),
                text=str(row["text"]),
            )
            for row in rows
        }

    @staticmethod
    def _sources(database: Database, project_id: str) -> tuple[ManifestSource, ...]:
        with database.connection() as connection:
            rows = connection.execute(
                """SELECT title,origin,locator FROM sources
                WHERE project_id=? AND included=1 ORDER BY imported_at,id""",
                (project_id,),
            ).fetchall()
        return tuple(
            ManifestSource(
                str(row["title"]),
                str(row["origin"]),
                None if row["locator"] is None else str(row["locator"]),
            )
            for row in rows
        )

    @staticmethod
    def _copy_episode_audio(root: Path, episode_id: str, stem: Path) -> Path | None:
        output = root / "output"
        for suffix in (".mp3", ".wav"):
            source = output / f"{episode_id}{suffix}"
            if source.is_file():
                destination = stem.with_suffix(suffix)
                destination.write_bytes(source.read_bytes())
                return destination
        return None


def _evidence_ids(raw: str) -> tuple[str, ...]:
    payload = json.loads(raw)
    if not isinstance(payload, list):
        return ()
    return tuple(str(value) for value in payload)
