from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.storage.database import Database
from deeper_dive.tts import FakeTTSProvider, TTSAudioResult, TTSProviderRegistry, TTSRequest, TTSVoice
from deeper_dive.tts_generation import TTSArtifactRepository, TTSGenerationStage, TTSTurn


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


def _registry(provider: FakeTTSProvider) -> TTSProviderRegistry:
    registry = TTSProviderRegistry()
    registry.register(provider)
    return registry


def _turn(provider: FakeTTSProvider, *, model: str | None = None) -> TTSTurn:
    return TTSTurn(
        "turn-1",
        "host-1",
        "hello from the host",
        provider.provider_id,
        "voice-a",
        model=model,
    )


class _WrongModelTTSProvider(FakeTTSProvider):
    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        return replace(super().synthesize(request), model="wrong-model")


class _MissingModelTTSProvider(FakeTTSProvider):
    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        return replace(super().synthesize(request), model=None)


class _InvalidFormatTTSProvider(FakeTTSProvider):
    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        return replace(super().synthesize(request), format="../wav")


def test_tts_stage_rejects_mismatched_returned_model_without_saving(tmp_path: Path) -> None:
    provider = _WrongModelTTSProvider(voices=(TTSVoice("voice-a", "Voice A"),))
    repository = TTSArtifactRepository(_database(tmp_path / "project.db"))
    cache_dir = tmp_path / "cache"
    stage = TTSGenerationStage(_registry(provider), repository, cache_dir, max_workers=1)

    with pytest.raises(ValueError, match="TTS model identity mismatch"):
        stage.generate("run", (_turn(provider, model="expected-model"),))

    assert repository.get_by_turn_id("turn-1") is None
    assert not list(cache_dir.glob("*"))


def test_tts_stage_rejects_unreported_requested_model_without_saving(tmp_path: Path) -> None:
    provider = _MissingModelTTSProvider(voices=(TTSVoice("voice-a", "Voice A"),))
    repository = TTSArtifactRepository(_database(tmp_path / "project.db"))
    cache_dir = tmp_path / "cache"
    stage = TTSGenerationStage(_registry(provider), repository, cache_dir, max_workers=1)

    with pytest.raises(ValueError, match="TTS model identity unavailable"):
        stage.generate("run", (_turn(provider, model="expected-model"),))

    assert repository.get_by_turn_id("turn-1") is None
    assert not list(cache_dir.glob("*"))


def test_tts_stage_persists_positive_model_identity_and_format(tmp_path: Path) -> None:
    provider = FakeTTSProvider(voices=(TTSVoice("voice-a", "Voice A"),))
    repository = TTSArtifactRepository(_database(tmp_path / "project.db"))
    stage = TTSGenerationStage(_registry(provider), repository, tmp_path / "cache", max_workers=1)

    (artifact,) = stage.generate("run", (_turn(provider, model="fake-v1"),))
    persisted = repository.get_by_turn_id("turn-1")

    assert artifact.model == "fake-v1"
    assert artifact.format == "wav"
    assert artifact.path.suffix == ".wav"
    assert persisted is not None
    assert persisted.model == "fake-v1"
    assert persisted.format == "wav"
    assert persisted.path == artifact.path


def test_tts_stage_rejects_invalid_reported_format_without_saving(tmp_path: Path) -> None:
    provider = _InvalidFormatTTSProvider(voices=(TTSVoice("voice-a", "Voice A"),))
    repository = TTSArtifactRepository(_database(tmp_path / "project.db"))
    cache_dir = tmp_path / "cache"
    stage = TTSGenerationStage(_registry(provider), repository, cache_dir, max_workers=1)

    with pytest.raises(ValueError, match="invalid audio format"):
        stage.generate("run", (_turn(provider),))

    assert repository.get_by_turn_id("turn-1") is None
    assert not list(cache_dir.glob("*"))
