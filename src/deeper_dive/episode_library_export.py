"""Episode-specific export workflow shared by library surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deeper_dive.export import EpisodeExporter, ManifestSource, TranscriptTurn
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
                """SELECT t.text,COALESCE(h.display_name,t.speaker_id) AS speaker_name
                FROM conversation_turns t LEFT JOIN hosts h ON h.id=t.speaker_id
                WHERE t.episode_id=? ORDER BY t.segment_ordinal,t.turn_ordinal""",
                (episode_id,),
            ).fetchall()
        return tuple(TranscriptTurn(str(row["speaker_name"]), str(row["text"])) for row in rows)

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
