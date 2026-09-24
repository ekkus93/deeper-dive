"""Resumable per-turn TTS generation with durable cache and checkpoints."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeper_dive.storage.database import Database
from deeper_dive.tts import TTSAudioResult, TTSProviderRegistry, TTSRequest

TTS_ARTIFACT_STATUS_COMPLETE = "complete"
TTS_ARTIFACT_LEGACY_SUCCESS_STATUSES = ("completed",)


@dataclass(frozen=True, slots=True)
class TTSTurn:
    turn_id: str
    host_id: str
    text: str
    provider_id: str
    voice: str
    model: str | None = None
    settings: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TTSArtifact:
    turn_id: str
    artifact_id: str
    cache_key: str
    status: str
    path: Path
    provider_id: str
    voice: str
    model: str | None


class TTSArtifactRepository:
    """Durable TTS artifact/status boundary."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        self.normalize_legacy_success_statuses()

    def normalize_legacy_success_statuses(self) -> int:
        """Normalize persisted legacy success values to the canonical status."""

        placeholders = ",".join("?" for _ in TTS_ARTIFACT_LEGACY_SUCCESS_STATUSES)
        with self.database.transaction() as db:
            cursor = db.execute(
                f"UPDATE tts_artifacts SET status=? WHERE status IN ({placeholders})",
                (TTS_ARTIFACT_STATUS_COMPLETE, *TTS_ARTIFACT_LEGACY_SUCCESS_STATUSES),
            )
        return cursor.rowcount

    def get_by_cache_key(self, cache_key: str) -> TTSArtifact | None:
        accepted = (TTS_ARTIFACT_STATUS_COMPLETE, *TTS_ARTIFACT_LEGACY_SUCCESS_STATUSES)
        placeholders = ",".join("?" for _ in accepted)
        with self.database.connection() as db:
            row = db.execute(
                f"SELECT * FROM tts_artifacts WHERE cache_key=? AND status IN ({placeholders})",
                (cache_key, *accepted),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def save(self, artifact: TTSArtifact) -> None:
        artifact = self._with_canonical_status(artifact)
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO tts_artifacts(
                    turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
                ) VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(turn_id) DO UPDATE SET
                    artifact_id=excluded.artifact_id, cache_key=excluded.cache_key,
                    status=excluded.status, path=excluded.path,
                    provider_id=excluded.provider_id, voice=excluded.voice, model=excluded.model""",
                (
                    artifact.turn_id,
                    artifact.artifact_id,
                    artifact.cache_key,
                    artifact.status,
                    str(artifact.path),
                    artifact.provider_id,
                    artifact.voice,
                    artifact.model,
                ),
            )

    def mark_checkpoint(self, run_id: str, turn_id: str) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT OR IGNORE INTO generation_run_units(run_id,stage,unit_id,completed_at)
                VALUES (?, 'tts', ?, datetime('now'))""",
                (run_id, turn_id),
            )

    @staticmethod
    def _with_canonical_status(artifact: TTSArtifact) -> TTSArtifact:
        if artifact.status == TTS_ARTIFACT_STATUS_COMPLETE:
            return artifact
        if artifact.status in TTS_ARTIFACT_LEGACY_SUCCESS_STATUSES:
            return TTSArtifact(
                turn_id=artifact.turn_id,
                artifact_id=artifact.artifact_id,
                cache_key=artifact.cache_key,
                status=TTS_ARTIFACT_STATUS_COMPLETE,
                path=artifact.path,
                provider_id=artifact.provider_id,
                voice=artifact.voice,
                model=artifact.model,
            )
        return artifact

    @staticmethod
    def _from_row(row: Any) -> TTSArtifact:
        status = str(row["status"])
        if status in TTS_ARTIFACT_LEGACY_SUCCESS_STATUSES:
            status = TTS_ARTIFACT_STATUS_COMPLETE
        return TTSArtifact(
            turn_id=str(row["turn_id"]),
            artifact_id=str(row["artifact_id"]),
            cache_key=str(row["cache_key"]),
            status=status,
            path=Path(str(row["path"])),
            provider_id=str(row["provider_id"]),
            voice=str(row["voice"]),
            model=None if row["model"] is None else str(row["model"]),
        )


class TTSGenerationStage:
    """Generate missing turn audio while preserving valid cached work."""

    def __init__(
        self,
        registry: TTSProviderRegistry,
        repository: TTSArtifactRepository,
        cache_dir: Path,
        *,
        max_workers: int = 2,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self.registry = registry
        self.repository = repository
        self.cache_dir = cache_dir
        self.max_workers = max_workers

    def generate(self, run_id: str, turns: tuple[TTSTurn, ...]) -> tuple[TTSArtifact, ...]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        resolved: dict[str, TTSArtifact] = {}
        missing: list[tuple[TTSTurn, str]] = []
        for turn in turns:
            key = self.cache_key(turn)
            cached = self.repository.get_by_cache_key(key)
            if cached is not None and cached.path.is_file() and cached.path.stat().st_size > 0:
                artifact = self._artifact_for_current_turn(turn, key, cached)
                self.repository.save(artifact)
                resolved[turn.turn_id] = artifact
                self.repository.mark_checkpoint(run_id, turn.turn_id)
            else:
                missing.append((turn, key))

        if self.max_workers == 1:
            for turn, key in missing:
                artifact = self._synthesize(run_id, turn, key)
                resolved[artifact.turn_id] = artifact
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._synthesize, run_id, turn, key): turn.turn_id
                    for turn, key in missing
                }
                for future in as_completed(futures):
                    artifact = future.result()
                    resolved[artifact.turn_id] = artifact
        return tuple(resolved[turn.turn_id] for turn in turns)

    @staticmethod
    def _artifact_for_current_turn(
        turn: TTSTurn, key: str, cached: TTSArtifact
    ) -> TTSArtifact:
        return TTSArtifact(
            turn_id=turn.turn_id,
            artifact_id=cached.artifact_id,
            cache_key=key,
            status=TTS_ARTIFACT_STATUS_COMPLETE,
            path=cached.path,
            provider_id=cached.provider_id,
            voice=cached.voice,
            model=cached.model,
        )

    def _synthesize(self, run_id: str, turn: TTSTurn, key: str) -> TTSArtifact:
        provider = self.registry.get(turn.provider_id)
        settings = turn.settings or {}
        result = provider.synthesize(
            TTSRequest(
                text=turn.text,
                voice=turn.voice,
                model=turn.model,
                response_format=str(settings.get("response_format", "wav")),
                sample_rate_hz=settings.get("sample_rate_hz"),
            )
        )
        artifact = self._persist_result(turn, key, result)
        self.repository.save(artifact)
        self.repository.mark_checkpoint(run_id, turn.turn_id)
        return artifact

    def _persist_result(self, turn: TTSTurn, key: str, result: TTSAudioResult) -> TTSArtifact:
        if not result.audio:
            raise ValueError(f"TTS provider returned empty audio for turn {turn.turn_id}")
        suffix = result.format.lower().lstrip(".") or "bin"
        artifact_id = f"tts-{key[:24]}"
        path = self.cache_dir / f"{artifact_id}.{suffix}"
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(result.audio)
        temporary.replace(path)
        return TTSArtifact(
            turn_id=turn.turn_id,
            artifact_id=artifact_id,
            cache_key=key,
            status=TTS_ARTIFACT_STATUS_COMPLETE,
            path=path,
            provider_id=turn.provider_id,
            voice=turn.voice,
            model=turn.model,
        )

    @staticmethod
    def cache_key(turn: TTSTurn) -> str:
        payload = {
            "text": turn.text,
            "voice": turn.voice,
            "provider": turn.provider_id,
            "model": turn.model,
            "settings": turn.settings or {},
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()
