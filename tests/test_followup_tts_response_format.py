from __future__ import annotations

import wave
from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.composition import ProductionComposition, _tts_turn_for_host
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import HostProfile, create_host_from_preset
from deeper_dive.openai_compatible_tts import OpenAICompatibleTTSProvider
from deeper_dive.pipeline import PipelineContext
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.tts import FakeTTSProvider, TTSProvider, TTSVoice
from deeper_dive.tts_generation import TTSArtifactRepository
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class RecordingFakeFactory(ProviderFactory):
    def __init__(self) -> None:
        super().__init__(environ={})
        self.provider: FakeTTSProvider | None = None

    def _tts(self, name: str, kind: str, config: ProviderConfig) -> TTSProvider:
        if kind != "fake-tts":
            return super()._tts(name, kind, config)
        voices = tuple(TTSVoice(voice, voice) for voice in config.voices)
        self.provider = FakeTTSProvider(provider_id=name, voices=voices or None)
        return self.provider


class RecordingCompatibleFactory(ProviderFactory):
    def __init__(self) -> None:
        super().__init__(environ={})
        self.payloads: list[dict[str, object]] = []

    def _tts(self, name: str, kind: str, config: ProviderConfig) -> TTSProvider:
        if kind != "openai-compatible-tts":
            return super()._tts(name, kind, config)

        def request(
            url: str,
            payload: dict[str, object],
            headers: dict[str, str],
            timeout: float,
        ) -> tuple[bytes, str | None]:
            _ = (url, headers, timeout)
            self.payloads.append(dict(payload))
            return b"deterministic-mp3", "audio/mpeg"

        return OpenAICompatibleTTSProvider(
            provider_id=name,
            base_url=config.base_url or "https://tts.example.test",
            model=config.default_model or "tts-model",
            voices=config.voices or ("voice-a",),
            response_format=config.response_format,
            request_binary=request,
        )


def test_duplicate_cache_reuse_composes_and_exports_every_turn(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    voices=("voice-a",),
                )
            }
        )
    )
    factory = RecordingFakeFactory()
    composition = ProductionComposition.build(data_dir, provider_factory=factory)
    project_id, episode_id, _host = _episode_with_turn(
        composition,
        provider_id="speech",
        voice="voice-a",
        text="shared duplicate speech",
    )
    database = composition.database_for_project(project_id)
    first_turn = HostTurnService(database).list_turns(episode_id)[0]
    with database.transaction() as db:
        db.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                "turn-r5-duplicate",
                episode_id,
                0,
                1,
                first_turn.speaker_id,
                first_turn.text,
                "[]",
            ),
        )

    composition.generate_episode_tts(
        project_id,
        PipelineContext("run-r5-cache", episode_id, "tts"),
    )

    assert factory.provider is not None
    assert len(factory.provider.requests) == 1
    artifact_repository = TTSArtifactRepository(database)
    first_artifact = artifact_repository.get_by_turn_id(first_turn.id)
    second_artifact = artifact_repository.get_by_turn_id("turn-r5-duplicate")
    assert first_artifact is not None
    assert second_artifact is not None
    assert first_artifact.cache_key == second_artifact.cache_key
    assert first_artifact.artifact_id == second_artifact.artifact_id
    assert first_artifact.path == second_artifact.path

    composition.compose_episode_audio(
        project_id,
        PipelineContext("run-r5-cache", episode_id, "composition"),
    )

    episode = HostEpisodeRepository(database).get_episode(episode_id)
    assert episode is not None
    run = GenerationRunRecord(
        "run-r5-cache",
        episode_id,
        "export",
        "completed",
        "2026-09-27T00:00:00Z",
        "2026-09-27T00:00:00Z",
    )
    exported = EpisodeLibraryExportService(composition.service.workspaces).export(
        project_id,
        episode,
        run,
    )

    assert exported.audio is not None
    with wave.open(str(exported.audio), "rb") as audio:
        assert audio.getnframes() > 0
        assert audio.getframerate() == 24000
    transcript = exported.transcript.read_text(encoding="utf-8")
    assert transcript.count("shared duplicate speech") == 2


def test_production_tts_blocks_configured_openai_compatible_mp3(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "speech": ProviderConfig(
                    provider_type="openai-compatible-tts",
                    base_url="https://tts.example.test",
                    default_model="tts-model",
                    voices=("voice-a",),
                    response_format="mp3",
                )
            }
        )
    )
    factory = RecordingCompatibleFactory()
    composition = ProductionComposition.build(data_dir, provider_factory=factory)
    project_id, episode_id, host = _episode_with_turn(
        composition,
        provider_id="speech",
        voice="voice-a",
        text="configured mp3",
    )
    database = composition.database_for_project(project_id)
    turn = HostTurnService(database).list_turns(episode_id)[0]

    production_turn = _tts_turn_for_host(composition, host, turn)
    assert production_turn.model == "tts-model"
    assert production_turn.settings == {"response_format": "mp3"}

    with pytest.raises(ValueError, match="WAV only"):
        composition.generate_episode_tts(
            project_id,
            PipelineContext("run-r5", episode_id, "tts"),
        )
    assert factory.payloads == []
    assert TTSArtifactRepository(database).get_by_turn_id(turn.id) is None


def test_production_tts_default_wav_keeps_implicit_default_identity(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    voices=("voice-a",),
                    response_format="wav",
                )
            }
        )
    )
    composition = ProductionComposition.build(
        data_dir, provider_factory=ProviderFactory(environ={})
    )
    project_id, episode_id, host = _episode_with_turn(
        composition,
        provider_id="speech",
        voice="voice-a",
        text="default wav",
    )
    database = composition.database_for_project(project_id)
    turn = HostTurnService(database).list_turns(episode_id)[0]

    production_turn = _tts_turn_for_host(composition, host, turn)
    assert production_turn.settings is None

    composition.generate_episode_tts(
        project_id,
        PipelineContext("run-r5", episode_id, "tts"),
    )
    artifact = TTSArtifactRepository(database).get_by_turn_id(turn.id)
    assert artifact is not None
    assert artifact.path.suffix == ".wav"
    assert artifact.format == "wav"


def test_production_kitten_rejects_configured_non_wav_before_success(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "speech": ProviderConfig(
                    provider_type="kitten",
                    response_format="mp3",
                )
            }
        )
    )
    composition = ProductionComposition.build(
        data_dir, provider_factory=ProviderFactory(environ={})
    )
    project_id, episode_id, host = _episode_with_turn(
        composition,
        provider_id="speech",
        voice="Jasper",
        text="kitten rejects mp3",
    )
    database = composition.database_for_project(project_id)
    turn = HostTurnService(database).list_turns(episode_id)[0]
    assert _tts_turn_for_host(composition, host, turn).settings == {"response_format": "mp3"}

    with pytest.raises(ValueError, match="WAV only"):
        composition.generate_episode_tts(
            project_id,
            PipelineContext("run-r5", episode_id, "tts"),
        )
    assert TTSArtifactRepository(database).get_by_turn_id(turn.id) is None


def _episode_with_turn(
    composition: ProductionComposition,
    *,
    provider_id: str,
    voice: str,
    text: str,
) -> tuple[str, str, HostProfile]:
    project = composition.service.create_project("R5 TTS")
    host = create_host_from_preset("curious_explainer", project.id)
    host_record = replace(host.to_record(), tts_provider=provider_id, tts_voice=voice)
    composition.service.hosts(project.id).create_host(host_record)
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(title="R5 episode", host_ids=(host.id,)),
    )
    database = composition.database_for_project(project.id)
    HostTurnService(database)
    with database.transaction() as db:
        db.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("turn-r5", episode.id, 0, 0, host.id, text, "[]"),
        )
    return project.id, episode.id, HostProfile.from_record(host_record)
