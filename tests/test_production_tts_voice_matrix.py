from __future__ import annotations

import wave
from pathlib import Path

import pytest

from deeper_dive import composition as composition_module
from deeper_dive.composition import ProductionComposition
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import HostProfile
from deeper_dive.pipeline import PipelineContext
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_production_tts_stage_routes_distinct_configured_provider_voices(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "calm-tts": ProviderConfig(provider_type="fake-tts", voices=("calm",)),
                "bright-tts": ProviderConfig(provider_type="fake-tts", voices=("bright",)),
            }
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Voice matrix")
    database = composition.database_for_project(project.id)
    repository = HostEpisodeRepository(database)
    HostTurnService(database)
    calm = HostProfile(
        "host-calm",
        project.id,
        "Calm Host",
        tts_provider="calm-tts",
        tts_voice="calm",
    )
    bright = HostProfile(
        "host-bright",
        project.id,
        "Bright Host",
        tts_provider="bright-tts",
        tts_voice="bright",
    )
    repository.create_host(calm.to_record())
    repository.create_host(bright.to_record())
    episode = EpisodeRecord("episode-voice-matrix", project.id, "Episode", "t", "t")
    repository.create_episode(episode, [calm.id, bright.id])
    composition.generation_run_repository(project.id).create(
        GenerationRunRecord("run-voice-matrix", episode.id, "tts", "running", "t", "t")
    )
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("turn-calm", episode.id, 0, 0, calm.id, "calm voice text", "[]"),
        )
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("turn-bright", episode.id, 0, 1, bright.id, "bright voice text", "[]"),
        )

    composition_module._tts_stage(
        composition.service,
        project.id,
        PipelineContext("run-voice-matrix", episode.id, "tts"),
    )

    with database.connection() as connection:
        rows = connection.execute(
            "SELECT turn_id,provider_id,voice,path FROM tts_artifacts ORDER BY turn_id"
        ).fetchall()
    assert [(row["turn_id"], row["provider_id"], row["voice"]) for row in rows] == [
        ("turn-bright", "bright-tts", "bright"),
        ("turn-calm", "calm-tts", "calm"),
    ]
    by_turn = {row["turn_id"]: row for row in rows}
    assert b"bright\nbright voice text" in Path(str(by_turn["turn-bright"]["path"])).read_bytes()
    assert b"calm\ncalm voice text" in Path(str(by_turn["turn-calm"]["path"])).read_bytes()


def test_production_tts_stage_rejects_missing_host_tts_assignment(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(providers={"speech": ProviderConfig(provider_type="fake-tts")})
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Missing host TTS")
    database = composition.database_for_project(project.id)
    repository = HostEpisodeRepository(database)
    HostTurnService(database)
    host = HostProfile("host-missing", project.id, "Missing Assignment")
    repository.create_host(host.to_record())
    episode = EpisodeRecord("episode-missing-tts", project.id, "Episode", "t", "t")
    repository.create_episode(episode, [host.id])
    composition.generation_run_repository(project.id).create(
        GenerationRunRecord("run-missing-tts", episode.id, "tts", "running", "t", "t")
    )
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("turn-missing-tts", episode.id, 0, 0, host.id, "missing assignment", "[]"),
        )

    with pytest.raises(ValueError, match="no TTS provider"):
        composition_module._tts_stage(
            composition.service,
            project.id,
            PipelineContext("run-missing-tts", episode.id, "tts"),
        )
