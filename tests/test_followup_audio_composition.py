from __future__ import annotations

import wave
from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.audio_normalization import CanonicalAudio
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.composition import _composition_stage, ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.export import EpisodeExporter
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.host_turn import HostTurnService
from deeper_dive.pipeline import PipelineContext
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.tts_generation import (
    TTS_ARTIFACT_STATUS_COMPLETE,
    TTSArtifact,
    TTSArtifactRepository,
    TTSGenerationStage,
    TTSTurn,
)
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_composition_stage_writes_single_valid_wav_from_two_turn_artifacts(
    tmp_path: Path,
) -> None:
    composition, project_id, episode_id, host_id = _composition_with_episode(tmp_path)
    database = composition.database_for_project(project_id)
    _insert_turn(database, episode_id, "turn-a", 0, host_id, "first composed turn")
    _insert_turn(database, episode_id, "turn-b", 1, host_id, "second composed turn")
    repository = TTSArtifactRepository(database)
    first = _save_artifact(
        repository,
        tmp_path,
        turn_id="turn-a",
        host_id=host_id,
        text="first composed turn",
        frame_count=5,
    )
    second = _save_artifact(
        repository,
        tmp_path,
        turn_id="turn-b",
        host_id=host_id,
        text="second composed turn",
        frame_count=7,
    )

    _composition_stage(
        composition.service,
        project_id,
        PipelineContext("run-r4", episode_id, "composition"),
    )

    episode_audio = (
        composition.service.workspaces.project_root(project_id) / "output" / f"{episode_id}.wav"
    )
    assert episode_audio.is_file()
    with wave.open(str(episode_audio), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 24000
        assert wav.getnframes() == first + second
    timeline = AudioTimelineRepository(database).get(episode_id)
    assert timeline is not None
    assert [placement.item.artifact_id for placement in timeline.placements] == [
        "artifact-turn-a",
        "artifact-turn-b",
    ]
    assert [placement.item.turn_id for placement in timeline.placements] == ["turn-a", "turn-b"]


def test_composition_stage_rejects_unsupported_non_wav_artifacts(tmp_path: Path) -> None:
    composition, project_id, episode_id, host_id = _composition_with_episode(tmp_path)
    database = composition.database_for_project(project_id)
    _insert_turn(database, episode_id, "turn-mp3", 0, host_id, "unsupported artifact")
    repository = TTSArtifactRepository(database)
    mp3_path = tmp_path / "turn-mp3.mp3"
    mp3_path.write_bytes(b"not really mp3")
    turn = TTSTurn("turn-mp3", host_id, "unsupported artifact", "speech", "voice-a")
    repository.save(
        TTSArtifact(
            turn_id=turn.turn_id,
            artifact_id="artifact-turn-mp3",
            cache_key=TTSGenerationStage.cache_key(turn),
            status=TTS_ARTIFACT_STATUS_COMPLETE,
            path=mp3_path,
            provider_id=turn.provider_id,
            voice=turn.voice,
            model=turn.model,
        )
    )

    with pytest.raises(ValueError, match="unsupported TTS artifact format"):
        _composition_stage(
            composition.service,
            project_id,
            PipelineContext("run-r4", episode_id, "composition"),
        )


def _composition_with_episode(tmp_path: Path) -> tuple[ProductionComposition, str, str, str]:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(providers={"speech": ProviderConfig(provider_type="fake-tts")})
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("R4 composition")
    host = create_host_from_preset("curious_explainer", project.id)
    host_record = replace(host.to_record(), tts_provider="speech", tts_voice="voice-a")
    composition.service.hosts(project.id).create_host(host_record)
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(title="R4 episode", host_ids=(host.id,)),
    )
    return composition, project.id, episode.id, host.id


def _insert_turn(
    database,
    episode_id: str,
    turn_id: str,
    ordinal: int,
    host_id: str,
    text: str,
) -> None:
    HostTurnService(database)
    with database.transaction() as db:
        db.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            (turn_id, episode_id, 0, ordinal, host_id, text, "[]"),
        )


def _save_artifact(
    repository: TTSArtifactRepository,
    tmp_path: Path,
    *,
    turn_id: str,
    host_id: str,
    text: str,
    frame_count: int,
) -> int:
    audio_path = tmp_path / f"{turn_id}.wav"
    EpisodeExporter.write_wav(
        audio_path,
        CanonicalAudio(
            pcm=b"\x01\x00" * frame_count,
            sample_rate_hz=24000,
            channels=1,
            sample_width_bytes=2,
            duration_seconds=frame_count / 24000,
            source_format="pcm_s16le",
            source_media_type="audio/wav",
        ),
    )
    turn = TTSTurn(turn_id, host_id, text, "speech", "voice-a")
    repository.save(
        TTSArtifact(
            turn_id=turn_id,
            artifact_id=f"artifact-{turn_id}",
            cache_key=TTSGenerationStage.cache_key(turn),
            status=TTS_ARTIFACT_STATUS_COMPLETE,
            path=audio_path,
            provider_id=turn.provider_id,
            voice=turn.voice,
            model=turn.model,
        )
    )
    return frame_count
