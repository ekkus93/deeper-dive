"""Resumable per-turn TTS generation with durable cache and checkpoints."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeper_dive.audio_normalization import normalize_wav
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
    format: str = ""


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
                f"""SELECT * FROM tts_artifacts
                WHERE cache_key=? AND status IN ({placeholders})
                ORDER BY turn_id LIMIT 1""",
                (cache_key, *accepted),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def get_by_turn_id(self, turn_id: str) -> TTSArtifact | None:
        with self.database.connection() as db:
            row = db.execute(
                "SELECT * FROM tts_artifacts WHERE turn_id=?",
                (turn_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def save(self, artifact: TTSArtifact) -> None:
        artifact = self._with_canonical_status(artifact)
        previous = self.get_by_turn_id(artifact.turn_id)
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO tts_artifacts(
                    turn_id,artifact_id,cache_key,status,path,provider_id,voice,model,format
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(turn_id) DO UPDATE SET
                    artifact_id=excluded.artifact_id, cache_key=excluded.cache_key,
                    status=excluded.status, path=excluded.path,
                    provider_id=excluded.provider_id, voice=excluded.voice,
                    model=excluded.model, format=excluded.format""",
                (
                    artifact.turn_id,
                    artifact.artifact_id,
                    artifact.cache_key,
                    artifact.status,
                    str(artifact.path),
                    artifact.provider_id,
                    artifact.voice,
                    artifact.model,
                    artifact.format,
                ),
            )
        if previous is not None and previous.path != artifact.path:
            self.collect_if_unreferenced(previous.path)

    def collect_if_unreferenced(self, path: Path) -> bool:
        """Delete an obsolete cache file only when no durable turn references it."""
        with self.database.connection() as db:
            row = db.execute(
                "SELECT 1 FROM tts_artifacts WHERE path=? LIMIT 1", (str(path),)
            ).fetchone()
        if row is not None:
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

    def delete_turn(self, turn_id: str) -> TTSArtifact | None:
        """Drop one turn reference and collect its file when it becomes unreachable."""
        previous = self.get_by_turn_id(turn_id)
        if previous is None:
            return None
        with self.database.transaction() as db:
            db.execute("DELETE FROM tts_artifacts WHERE turn_id=?", (turn_id,))
        self.collect_if_unreferenced(previous.path)
        return previous

    def mark_checkpoint(self, run_id: str, turn_id: str) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT OR IGNORE INTO generation_run_units(run_id,stage,unit_id,completed_at)
                SELECT ?, 'tts', ?, datetime('now')
                WHERE EXISTS (SELECT 1 FROM generation_runs WHERE id=?)""",
                (run_id, turn_id, run_id),
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
                format=artifact.format,
            )
        return artifact

    @staticmethod
    def _from_row(row: Any) -> TTSArtifact:
        status = str(row["status"])
        if status in TTS_ARTIFACT_LEGACY_SUCCESS_STATUSES:
            status = TTS_ARTIFACT_STATUS_COMPLETE
        path = Path(str(row["path"]))
        stored_format = str(row["format"]).strip().lower()
        return TTSArtifact(
            turn_id=str(row["turn_id"]),
            artifact_id=str(row["artifact_id"]),
            cache_key=str(row["cache_key"]),
            status=status,
            path=path,
            provider_id=str(row["provider_id"]),
            voice=str(row["voice"]),
            model=None if row["model"] is None else str(row["model"]),
            format=stored_format or path.suffix.lower().lstrip("."),
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
        missing_by_key: dict[str, list[TTSTurn]] = {}
        for turn in turns:
            requested_format = self._requested_format(turn)
            key = self.cache_key(turn)
            cached = self.repository.get_by_cache_key(key)
            if (
                cached is not None
                and cached.format == requested_format
                and cached.path.is_file()
                and cached.path.stat().st_size > 0
            ):
                artifact = self._artifact_for_current_turn(turn, key, cached)
                resolved[turn.turn_id] = artifact
                self.repository.save(artifact)
                self.repository.mark_checkpoint(run_id, turn.turn_id)
            else:
                missing_by_key.setdefault(key, []).append(turn)

        if self.max_workers == 1:
            for key, pending_turns in missing_by_key.items():
                artifact = self._synthesize(run_id, pending_turns[0], key)
                resolved[artifact.turn_id] = artifact
                self._reuse_for_duplicate_turns(run_id, key, pending_turns[1:], artifact, resolved)
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._synthesize, run_id, pending_turns[0], key): (
                        key,
                        pending_turns,
                    )
                    for key, pending_turns in missing_by_key.items()
                }
                for future in as_completed(futures):
                    key, pending_turns = futures[future]
                    artifact = future.result()
                    resolved[artifact.turn_id] = artifact
                    self._reuse_for_duplicate_turns(
                        run_id,
                        key,
                        pending_turns[1:],
                        artifact,
                        resolved,
                    )
        return tuple(resolved[turn.turn_id] for turn in turns)

    def _reuse_for_duplicate_turns(
        self,
        run_id: str,
        key: str,
        turns: list[TTSTurn],
        cached: TTSArtifact,
        resolved: dict[str, TTSArtifact],
    ) -> None:
        for turn in turns:
            artifact = self._artifact_for_current_turn(turn, key, cached)
            resolved[turn.turn_id] = artifact
            self.repository.save(artifact)
            self.repository.mark_checkpoint(run_id, turn.turn_id)

    @staticmethod
    def _artifact_for_current_turn(turn: TTSTurn, key: str, cached: TTSArtifact) -> TTSArtifact:
        return TTSArtifact(
            turn_id=turn.turn_id,
            artifact_id=cached.artifact_id,
            cache_key=key,
            status=TTS_ARTIFACT_STATUS_COMPLETE,
            path=cached.path,
            provider_id=cached.provider_id,
            voice=cached.voice,
            model=cached.model,
            format=cached.format,
        )

    def _synthesize(self, run_id: str, turn: TTSTurn, key: str) -> TTSArtifact:
        provider = self.registry.get(turn.provider_id)
        settings = turn.settings or {}
        requested_format = self._requested_format(turn)
        result = provider.synthesize(
            TTSRequest(
                text=turn.text,
                voice=turn.voice,
                model=turn.model,
                response_format=requested_format,
                sample_rate_hz=settings.get("sample_rate_hz"),
            )
        )
        self._validate_identity(turn, result)
        returned_format = self._validated_format(turn, result)
        if returned_format != requested_format:
            raise ValueError("TTS response format mismatch: expected WAV")
        if result.media_type.lower() not in {"audio/wav", "audio/x-wav", "audio/wave"}:
            raise ValueError("TTS response media type mismatch: expected WAV")
        if not (result.audio[:4] == b"RIFF" and result.audio[8:12] == b"WAVE"):
            raise ValueError("TTS response is not a WAV container")
        normalize_wav(result.audio, source_media_type=result.media_type)
        artifact = self._persist_result(turn, key, result)
        self.repository.save(artifact)
        self.repository.mark_checkpoint(run_id, turn.turn_id)
        return artifact

    @staticmethod
    def _requested_format(turn: TTSTurn) -> str:
        requested_format = (
            str((turn.settings or {}).get("response_format", "wav")).lower().lstrip(".")
        )
        if requested_format != "wav":
            raise ValueError("generation supports WAV only TTS response format")
        return requested_format

    @staticmethod
    def _validate_identity(turn: TTSTurn, result: TTSAudioResult) -> None:
        if result.provider != turn.provider_id:
            raise ValueError(
                f"TTS provider identity mismatch for turn {turn.turn_id}: "
                f"expected {turn.provider_id!r}, got {result.provider!r}"
            )
        if result.voice != turn.voice:
            raise ValueError(
                f"TTS voice identity mismatch for turn {turn.turn_id}: "
                f"expected {turn.voice!r}, got {result.voice!r}"
            )
        if turn.model is not None and result.model is None:
            raise ValueError(
                f"TTS model identity unavailable for turn {turn.turn_id}: expected {turn.model!r}"
            )
        if turn.model is not None and result.model != turn.model:
            raise ValueError(
                f"TTS model identity mismatch for turn {turn.turn_id}: "
                f"expected {turn.model!r}, got {result.model!r}"
            )

    def _persist_result(self, turn: TTSTurn, key: str, result: TTSAudioResult) -> TTSArtifact:
        if not result.audio:
            raise ValueError(f"TTS provider returned empty audio for turn {turn.turn_id}")
        suffix = self._validated_format(turn, result)
        artifact_id = f"tts-{key[:24]}"
        path = self.cache_dir / f"{artifact_id}.{suffix}"
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(result.audio)
        temporary.replace(path)
        if path.suffix.lower().lstrip(".") != suffix:
            raise ValueError(
                f"TTS artifact extension mismatch for turn {turn.turn_id}: "
                f"expected {suffix!r}, got {path.suffix!r}"
            )
        return TTSArtifact(
            turn_id=turn.turn_id,
            artifact_id=artifact_id,
            cache_key=key,
            status=TTS_ARTIFACT_STATUS_COMPLETE,
            path=path,
            provider_id=result.provider,
            voice=result.voice,
            model=result.model,
            format=suffix,
        )

    @staticmethod
    def _validated_format(turn: TTSTurn, result: TTSAudioResult) -> str:
        suffix = result.format.lower().lstrip(".")
        if not suffix:
            raise ValueError(f"TTS provider did not report audio format for turn {turn.turn_id}")
        if "/" in suffix or "\\" in suffix:
            raise ValueError(
                f"TTS provider reported invalid audio format for turn {turn.turn_id}: "
                f"{result.format!r}"
            )
        return suffix

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
