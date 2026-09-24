from pathlib import Path

from deeper_dive.storage.database import Database
from deeper_dive.tts_generation import TTS_ARTIFACT_STATUS_COMPLETE, TTSArtifactRepository


def test_repository_initialization_normalizes_persisted_legacy_success_status(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    database.initialize()
    with database.transaction() as db:
        db.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
            ) VALUES (?,?,?,?,?,?,?,?)""",
            ("turn", "artifact", "key", "completed", "legacy.wav", "fake", "voice", None),
        )

    TTSArtifactRepository(database)

    with database.connection() as db:
        row = db.execute("SELECT status FROM tts_artifacts WHERE turn_id='turn'").fetchone()
    assert row is not None
    assert row["status"] == TTS_ARTIFACT_STATUS_COMPLETE


def test_status_normalization_is_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    database.initialize()
    with database.transaction() as db:
        db.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
            ) VALUES (?,?,?,?,?,?,?,?)""",
            ("turn", "artifact", "key", "complete", "audio.wav", "fake", "voice", None),
        )

    repository = TTSArtifactRepository(database)

    assert repository.normalize_legacy_success_statuses() == 0
