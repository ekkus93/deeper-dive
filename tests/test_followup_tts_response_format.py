from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.composition import ProductionComposition, _tts_stage, _tts_turn_for_host
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import HostProfile, create_host_from_preset
from deeper_dive.openai_compatible_tts import OpenAICompatibleTTSProvider
from deeper_dive.pipeline import PipelineContext
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.tts import TTSProvider
from deeper_dive.tts_generation import TTSArtifactRepository
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


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
            self.payloads.append(dict(payload))
            return b"deterministic-mp3", "audio/mpeg"

        return OpenAICompatibleTTSProvider(
            provider_id=name,
            base_url=config.base_url or "http://localhost:9999/v1",
            model=config.default_model or "tts-1",
            voices=tuple(config.voices),
            response_format=config.response_format,
            timeout=config.timeout_seconds,
            request_binary=request,
        )


def test_production_tts_honors_configured_openai_compatible_mp3(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "speech": ProviderConfig(
                    provider_type="openai-compatible-tts",
                    base_url="http://localhost:9999/v1",
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

    _tts_stage(
        composition.service,
        project_id,
        PipelineContext("run-r5", episode_id, "tts"),
    )

    assert factory.payloads == [
        {
            "model": "tts-model",
            "input": "configured mp3",
            "voice": "voice-a",
            "response_format": "mp3",
        }
    ]
    artifact = TTSArtifactRepository(database).get_by_turn_id(turn.id)
    assert artifact is not None
    assert artifact.path.suffix == ".mp3"
    assert artifact.format == "mp3"
    assert artifact.provider_id == "speech"
    assert artifact.voice == "voice-a"
    assert artifact.model == "tts-model"


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

    _tts_stage(
        composition.service,
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
        _tts_stage(
            composition.service,
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
