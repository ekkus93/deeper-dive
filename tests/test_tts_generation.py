import inspect
from pathlib import Path

import pytest

from deeper_dive import composition
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimeline, AudioTimelineRepository, TimelineItem
from deeper_dive.director_decision import DirectorDecision
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry, TTSVoice
from deeper_dive.tts_generation import (
    TTS_ARTIFACT_STATUS_COMPLETE,
    TTSArtifact,
    TTSArtifactRepository,
    TTSGenerationStage,
    TTSTurn,
)


class _UnusedTurnProvider:
    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
        raise AssertionError("legacy compatibility test inserts turns directly")


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


def test_duplicate_cache_reuse_persists_one_row_per_turn(tmp_path: Path) -> None:
    provider = FakeTTSProvider(voices=(TTSVoice("v", "Voice"),))
    registry = TTSProviderRegistry()
    registry.register(provider)
    database = _database(tmp_path / "project.db")
    repository = TTSArtifactRepository(database)
    stage = TTSGenerationStage(registry, repository, tmp_path / "cache", max_workers=2)
    turns = (
        TTSTurn("t1", "h", "same text", provider.provider_id, "v"),
        TTSTurn("t2", "h", "same text", provider.provider_id, "v"),
    )

    first = stage.generate("run", turns)
    second = stage.generate("run", turns)

    assert len(provider.requests) == 1
    assert [item.turn_id for item in first] == ["t1", "t2"]
    assert first[0].cache_key == first[1].cache_key
    assert first[0].artifact_id == first[1].artifact_id
    assert first[0].path == first[1].path
    assert [item.artifact_id for item in second] == [item.artifact_id for item in first]
    with database.connection() as db:
        rows = db.execute(
            """SELECT turn_id,cache_key,artifact_id,path
            FROM tts_artifacts ORDER BY turn_id"""
        ).fetchall()
    assert [str(row["turn_id"]) for row in rows] == ["t1", "t2"]
    assert len({str(row["cache_key"]) for row in rows}) == 1
    assert len({str(row["artifact_id"]) for row in rows}) == 1
    assert len({str(row["path"]) for row in rows}) == 1


def test_cache_identity_covers_all_synthesis_inputs() -> None:
    base = TTSTurn(
        "t",
        "h",
        "text",
        "provider-a",
        "voice-a",
        model="model-a",
        settings={"response_format": "mp3", "sample_rate_hz": 24000},
    )
    variants = (
        TTSTurn(
            "t",
            "h",
            "changed text",
            "provider-a",
            "voice-a",
            model="model-a",
            settings={"response_format": "mp3", "sample_rate_hz": 24000},
        ),
        TTSTurn(
            "t",
            "h",
            "text",
            "provider-b",
            "voice-a",
            model="model-a",
            settings={"response_format": "mp3", "sample_rate_hz": 24000},
        ),
        TTSTurn(
            "t",
            "h",
            "text",
            "provider-a",
            "voice-b",
            model="model-a",
            settings={"response_format": "mp3", "sample_rate_hz": 24000},
        ),
        TTSTurn(
            "t",
            "h",
            "text",
            "provider-a",
            "voice-a",
            model="model-b",
            settings={"response_format": "mp3", "sample_rate_hz": 24000},
        ),
        TTSTurn(
            "t",
            "h",
            "text",
            "provider-a",
            "voice-a",
            model="model-a",
            settings={"response_format": "wav", "sample_rate_hz": 24000},
        ),
        TTSTurn(
            "t",
            "h",
            "text",
            "provider-a",
            "voice-a",
            model="model-a",
            settings={"response_format": "mp3", "sample_rate_hz": 48000},
        ),
    )

    base_key = TTSGenerationStage.cache_key(base)
    assert all(TTSGenerationStage.cache_key(variant) != base_key for variant in variants)


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
    base = TTSTurn("t", "h", "text", "p", "v", model="m", settings={"sample_rate_hz": 24000})
    changed = TTSTurn("t", "h", "text", "p", "v", model="m", settings={"sample_rate_hz": 48000})
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


def test_repository_saves_legacy_success_artifacts_with_canonical_status(tmp_path: Path) -> None:
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
        row = db.execute("SELECT status FROM tts_artifacts WHERE turn_id='t-canonical'").fetchone()

    assert row is not None
    assert row["status"] == TTS_ARTIFACT_STATUS_COMPLETE
    assert TTSArtifactRepository(database).get_by_cache_key("canonical-key") is not None


def test_legacy_success_artifacts_remain_exportable_and_timeline_visible(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    service.workspaces.initialize()
    project = service.create_project("Legacy artifact compatibility")
    episode = service.quick_deep_dive(project.id)
    root = service.workspaces.project_root(project.id)
    database = Database(root / "project.db")
    HostTurnService(database, _UnusedTurnProvider())
    host_id = HostEpisodeRepository(database).list_episode_host_ids(episode.id)[0]
    turn_id = "turn-legacy"
    legacy_audio = root / "output" / "tts" / "legacy-artifact.wav"
    legacy_audio.parent.mkdir(parents=True, exist_ok=True)
    legacy_audio.write_bytes(b"legacy turn audio")
    episode_audio = root / "output" / f"{episode.id}.wav"
    episode_audio.write_bytes(b"legacy episode audio")

    with database.transaction() as db:
        db.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            (turn_id, episode.id, 0, 0, host_id, "legacy artifact transcript", "[]"),
        )
        db.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                turn_id,
                "legacy-artifact",
                "legacy-key",
                "completed",
                str(legacy_audio),
                "fake-tts",
                "voice-a",
                None,
            ),
        )
    run = GenerationRunRecord("run-legacy", episode.id, "export", "completed", "t", "t")
    GenerationRunRepository(database).create(run)
    AudioTimelineRepository(database).save(
        AudioTimeline.build(
            episode.id,
            (
                TimelineItem.clip(
                    turn_id=turn_id,
                    host_id=host_id,
                    artifact_id="legacy-artifact",
                    duration_seconds=1.0,
                ),
            ),
        )
    )

    artifact = TTSArtifactRepository(database).get_by_cache_key("legacy-key")
    timeline = AudioTimelineRepository(database).get(episode.id)
    exported = EpisodeLibraryExportService(service.workspaces).export(project.id, episode, run)

    assert artifact is not None
    assert artifact.status == TTS_ARTIFACT_STATUS_COMPLETE
    assert timeline is not None
    assert timeline.placements[0].item.artifact_id == "legacy-artifact"
    assert exported.transcript.read_text(encoding="utf-8").count("legacy artifact transcript") == 1
    assert exported.audio is not None
    assert exported.audio.read_bytes() == b"legacy episode audio"


def test_production_tts_stage_uses_provider_generation_contract() -> None:
    source = inspect.getsource(composition._tts_stage)
    composition_source = inspect.getsource(composition._composition_stage)

    assert "TTSGenerationStage" in source
    assert "TTSArtifactRepository" in source
    assert "_deterministic_audio_bytes" not in source
    assert "deterministic-tts" not in source
    assert "_deterministic_audio_bytes" not in composition_source


@pytest.mark.parametrize(
    "format,audio,media_type",
    [
        ("mp3", b"ID3unexpected", "audio/mpeg"),
        ("pcm", b"raw", "audio/L16"),
        ("wav", b"ID3disguised", "audio/wav"),
        ("wav", b"RIFF0000WAVEbroken", "audio/wav"),
    ],
)
def test_returned_format_mismatch_leaves_no_success(tmp_path, format, audio, media_type):
    from deeper_dive.tts import TTSAudioResult

    class BadProvider(FakeTTSProvider):
        def synthesize(self, request):
            return TTSAudioResult(audio, media_type, format, self.provider_id, request.voice)

    provider = BadProvider(voices=(TTSVoice("v", "Voice"),))
    registry = TTSProviderRegistry()
    registry.register(provider)
    database = _database(tmp_path / "project.db")
    repository = TTSArtifactRepository(database)
    cache = tmp_path / "cache"
    stage = TTSGenerationStage(registry, repository, cache, max_workers=1)
    with pytest.raises(ValueError):
        stage.generate("run", (TTSTurn("bad", "h", "text", provider.provider_id, "v"),))
    assert repository.get_by_turn_id("bad") is None
    assert not list(cache.iterdir())
    with database.connection() as db:
        assert not db.execute("SELECT * FROM generation_run_units WHERE run_id='run'").fetchall()
