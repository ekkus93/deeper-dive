from pathlib import Path

from deeper_dive.storage.database import Database
from deeper_dive.tts_generation import (
    TTS_ARTIFACT_STATUS_COMPLETE,
    TTSArtifact,
    TTSArtifactRepository,
)


def test_repository_reads_canonical_complete_status_by_cache_key(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    repository = TTSArtifactRepository(database)
    path = tmp_path / "canonical.wav"
    path.write_bytes(b"canonical-audio")
    repository.save(
        TTSArtifact(
            turn_id="turn-canonical",
            artifact_id="artifact-canonical",
            cache_key="canonical-key",
            status=TTS_ARTIFACT_STATUS_COMPLETE,
            path=path,
            provider_id="fake-tts",
            voice="voice-a",
            model=None,
        )
    )

    artifact = repository.get_by_cache_key("canonical-key")

    assert artifact is not None
    assert artifact.status == TTS_ARTIFACT_STATUS_COMPLETE
    assert artifact.path == path
