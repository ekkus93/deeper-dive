from pathlib import Path

import pytest

from deeper_dive.storage.database import Database
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry, TTSVoice
from deeper_dive.tts_generation import (
    TTS_ARTIFACT_STATUS_COMPLETE,
    TTSArtifact,
    TTSArtifactRepository,
    TTSGenerationStage,
    TTSTurn,
)


def _database(path: Path) -> Database:
    database = Database(path)
    database.initialize()
    with database.transaction() as db:
        db.execute("INSERT INTO projects(id,name,created_at,modified_at) VALUES ('p','P','t','t')")
        db.execute(
            "INSERT INTO episodes(id,project_id,title,created_at,modified_at) "
            "VALUES ('e','p','E','t','t')"
        )
        db.execute(
            "INSERT INTO generation_runs(id,episode_id,stage,state,created_at,modified_at) "
            "VALUES ('run','e','tts','running','t','t')"
        )
    return database


def test_tts_stage_caches_and_checkpoints_each_turn(tmp_path: Path) -> None:
    provider = FakeTTSProvider(voices=(TTSVoice("v", "Voice"),))
    registry = TTSProviderRegistry()
    registry.register(provider)
    database = _database(tmp_path / "project.db")
    repository = TTSArtifactRepository(database)
    stage = TTSGenerationStage(registry, repository, tmp_path / "cache", max_workers=2)
    turns = (
        TTSTurn("t1", "h", "one", provider.provider_id, "v"),
        TTSTurn("t2", "h", "two", provider.provider_id, "v"),
    )

    first = stage.generate("run", turns)
    second = stage.generate("run", turns)

    assert len(provider.requests) == 2
    assert [item.artifact_id for item in first] == [item.artifact_id for item in second]
    assert all(item.path.is_file() for item in first)
    with database.connection() as db:
        rows = db.execute(
            "SELECT unit_id FROM generation_run_units "
            "WHERE run_id='run' AND stage='tts' ORDER BY unit_id"
        ).fetchall()
    assert [row["unit_id"] for row in rows] == ["t1", "t2"]


def test_failure_resumes_without_resynthesizing_completed_turns(tmp_path: Path) -> None:
    class FailingProvider(FakeTTSProvider):
        fail = True

        def synthesize(self, request):  # type: ignore[no-untyped-def]
            if request.text == "two" and self.fail:
                self.fail = False
                raise RuntimeError("synthetic failure")
            return super().synthesize(request)

    provider = FailingProvider(voices=(TTSVoice("v", "Voice"),))
    registry = TTSProviderRegistry()
    registry.register(provider)
    database = _database(tmp_path / "project.db")
    stage = TTSGenerationStage(
        registry, TTSArtifactRepository(database), tmp_path / "cache", max_workers=1
    )
    turns = (
        TTSTurn("t1", "h", "one", provider.provider_id, "v"),
        TTSTurn("t2", "h", "two", provider.provider_id, "v"),
        TTSTurn("t3", "h", "three", provider.provider_id, "v"),
    )

    with pytest.raises(RuntimeError, match="synthetic failure"):
        stage.generate("run", turns)
    requests_after_failure = [request.text for request in provider.requests]
    assert requests_after_failure == ["one"]

    result = stage.generate("run", turns)

    assert [request.text for request in provider.requests] == ["one", "two", "three"]
    assert [item.turn_id for item in result] == ["t1", "t2", "t3"]


def test_cache_identity_includes_settings(tmp_path: Path) -> None:
    base = TTSTurn(
        "t", "h", "text", "p", "v", model="m", settings={"sample_rate_hz": 24000}
    )
    changed = TTSTurn(
        "t", "h", "text", "p", "v", model="m", settings={"sample_rate_hz": 48000}
    )
    assert TTSGenerationStage.cache_key(base) != TTSGenerationStage.cache_key(changed)


def test_repository_reads_legacy_completed_status_as_success(tmp_path: Path) -> None:
    database = _database(tmp_path / "project.db")
    path = tmp_path / "legacy.wav"
    path.write_bytes(b"legacy-audio")
    with database.transaction() as db:
        db.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                "t-legacy",
                "legacy-artifact",
                "legacy-key",
                "completed",
                str(path),
                "fake",
                "v",
                None,
            ),
        )

    artifact = TTSArtifactRepository(database).get_by_cache_key("legacy-key")

    assert artifact is not None
    assert artifact.status == TTS_ARTIFACT_STATUS_COMPLETE
    assert artifact.path == path


def test_repository_saves_legacy_success_artifacts_with_canonical_status(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path / "project.db")
    path = tmp_path / "artifact.wav"
    path.write_bytes(b"audio")
    repository = TTSArtifactRepository(database)

    repository.save(
        TTSArtifact(
            turn_id="t-canonical",
            artifact_id="artifact",
            cache_key="canonical-key",
            status="completed",
            path=path,
            provider_id="fake",
            voice="v",
            model=None,
        )
    )

    with database.connection() as db:
        row = db.execute(
            "SELECT status FROM tts_artifacts WHERE turn_id='t-canonical'"
        ).fetchone()

    assert row is not None
    assert row["status"] == TTS_ARTIFACT_STATUS_COMPLETE
    assert TTSArtifactRepository(database).get_by_cache_key("canonical-key") is not None
