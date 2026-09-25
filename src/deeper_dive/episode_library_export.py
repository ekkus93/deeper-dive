"""Episode-specific export workflow shared by library surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from deeper_dive.export import (
    EpisodeExporter,
    ManifestSource,
    TranscriptClaim,
    TranscriptSourcePassage,
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
                "provenance": exporter.transcript_provenance(turns),
            },
        )
        audio = self._copy_episode_audio(root, episode.id, stem)
        return EpisodeExportResult(transcript, manifest, metadata, audio)

    @classmethod
    def _turns(cls, database: Database, episode_id: str) -> tuple[TranscriptTurn, ...]:
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
        turn_ids = tuple(str(row["id"]) for row in rows)
        claims_by_turn = cls._claims(database, turn_ids)
        passage_ids: list[str] = []
        evidence_by_turn: dict[str, tuple[str, ...]] = {}
        for row in rows:
            turn_id = str(row["id"])
            evidence_ids = cls._json_ids(row["evidence_ids_json"])
            evidence_by_turn[turn_id] = evidence_ids
            passage_ids.extend(evidence_ids)
            for claim in claims_by_turn.get(turn_id, ()):  # claim evidence is transcript provenance too
                passage_ids.extend(claim.supporting_ids)
                passage_ids.extend(claim.contradicting_ids)
        passages = cls._passages(database, tuple(dict.fromkeys(passage_ids)))
        return tuple(
            TranscriptTurn(
                host=str(row["speaker_name"]),
                text=str(row["text"]),
                turn_id=str(row["id"]),
                speaker_id=str(row["speaker_id"]),
                segment_ordinal=int(row["segment_ordinal"]),
                turn_ordinal=int(row["turn_ordinal"]),
                evidence_ids=evidence_by_turn[str(row["id"])],
                claims=claims_by_turn.get(str(row["id"]), ()),
                source_passages=cls._source_passages_for_turn(
                    evidence_by_turn[str(row["id"])],
                    claims_by_turn.get(str(row["id"]), ()),
                    passages,
                ),
            )
            for row in rows
        )

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

    @classmethod
    def _claims(
        cls,
        database: Database,
        turn_ids: tuple[str, ...],
    ) -> dict[str, tuple[TranscriptClaim, ...]]:
        if not turn_ids:
            return {}
        placeholders = ",".join("?" for _ in turn_ids)
        with database.connection() as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='material_claims'"
            ).fetchone()
            verification_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='claim_verifications'"
            ).fetchone()
            if table is None:
                return {}
            if verification_table is None:
                rows = connection.execute(
                    f"""SELECT id,turn_id,text,NULL AS state,NULL AS rationale,
                    NULL AS supporting_evidence_ids_json,NULL AS contradicting_evidence_ids_json
                    FROM material_claims WHERE turn_id IN ({placeholders})
                    ORDER BY turn_id,span_start,id""",
                    turn_ids,
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""SELECT mc.id,mc.turn_id,mc.text,cv.state,cv.rationale,
                    cv.supporting_evidence_ids_json,cv.contradicting_evidence_ids_json
                    FROM material_claims mc LEFT JOIN claim_verifications cv ON cv.claim_id=mc.id
                    WHERE mc.turn_id IN ({placeholders}) ORDER BY mc.turn_id,mc.span_start,mc.id""",
                    turn_ids,
                ).fetchall()
        grouped: dict[str, list[TranscriptClaim]] = {}
        for row in rows:
            grouped.setdefault(str(row["turn_id"]), []).append(
                TranscriptClaim(
                    claim_id=str(row["id"]),
                    text=str(row["text"]),
                    state="unverified" if row["state"] is None else str(row["state"]),
                    rationale="" if row["rationale"] is None else str(row["rationale"]),
                    supporting_ids=cls._json_ids(row["supporting_evidence_ids_json"]),
                    contradicting_ids=cls._json_ids(row["contradicting_evidence_ids_json"]),
                )
            )
        return {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    def _passages(
        database: Database,
        chunk_ids: tuple[str, ...],
    ) -> dict[str, TranscriptSourcePassage]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        with database.connection() as connection:
            rows = connection.execute(
                f"""SELECT c.id,c.text,c.location,s.title,s.origin
                FROM source_chunks c JOIN sources s ON s.id=c.source_id
                WHERE c.id IN ({placeholders})""",
                chunk_ids,
            ).fetchall()
        return {
            str(row["id"]): TranscriptSourcePassage(
                chunk_id=str(row["id"]),
                source_title=str(row["title"]),
                origin=str(row["origin"]),
                location=None if row["location"] is None else str(row["location"]),
                text=str(row["text"]),
            )
            for row in rows
        }

    @staticmethod
    def _source_passages_for_turn(
        evidence_ids: tuple[str, ...],
        claims: tuple[TranscriptClaim, ...],
        passages: dict[str, TranscriptSourcePassage],
    ) -> tuple[TranscriptSourcePassage, ...]:
        relations: dict[str, list[str]] = {}
        for chunk_id in evidence_ids:
            relations.setdefault(chunk_id, []).append("turn citation")
        for claim in claims:
            for chunk_id in claim.supporting_ids:
                relations.setdefault(chunk_id, []).append(f"supports claim {claim.claim_id}")
            for chunk_id in claim.contradicting_ids:
                relations.setdefault(chunk_id, []).append(f"contradicts claim {claim.claim_id}")
        result: list[TranscriptSourcePassage] = []
        for chunk_id, labels in relations.items():
            passage = passages.get(chunk_id)
            if passage is None:
                continue
            result.append(
                TranscriptSourcePassage(
                    chunk_id=passage.chunk_id,
                    source_title=passage.source_title,
                    origin=passage.origin,
                    location=passage.location,
                    text=passage.text,
                    relation=", ".join(dict.fromkeys(labels)),
                )
            )
        return tuple(result)

    @staticmethod
    def _json_ids(value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        return tuple(str(item) for item in json.loads(str(value)))
