from __future__ import annotations

import json
from pathlib import Path

from deeper_dive.audio_timeline import AudioTimeline, AudioTimelineRepository, TimelineItem
from deeper_dive.host_turn import HostTurnService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodeRecord,
    HostEpisodeRepository,
    HostProfileRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.tts_generation import TTS_ARTIFACT_STATUS_COMPLETE, TTSArtifactRepository
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_current_provider_config_round_trips_with_concrete_adapter_identity(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    expected = UserConfig(
        providers={
            "dialogue": ProviderConfig(provider_type="fake", default_model="fake-v1"),
            "speech": ProviderConfig(
                provider_type="fake-tts",
                voices=("voice-a",),
                response_format="wav",
            ),
        },
        defaults={"episode_planning": "dialogue:fake-v1"},
    )
    store = UserConfigStore(path)
    store.save(expected)

    assert store.load() == expected


def test_existing_episode_run_turn_identity_timeline_and_legacy_tts_rows_load(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("project", "Legacy project", "t0", "t0"))
    episodes = HostEpisodeRepository(database)
    episodes.create_host(HostProfileRecord("host", "project", "Legacy Host"))
    episodes.create_episode(
        EpisodeRecord("episode", "project", "Legacy Episode", "t0", "t0"),
        ["host"],
    )
    runs = GenerationRunRepository(database)
    runs.create(GenerationRunRecord("run", "episode", "export", "completed", "t0", "t1"))
    audio = tmp_path / "legacy.wav"
    audio.write_bytes(b"legacy audio")

    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("turn", "episode", 0, 0, "host", "legacy turn", json.dumps(["chunk-old"])),
        )
        connection.execute(
            """INSERT INTO conversation_turn_provider_identity(turn_id,provider_id,model)
            VALUES (?,?,?)""",
            ("turn", "legacy-provider", "legacy-model"),
        )
        connection.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model,format
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                "turn",
                "artifact",
                "cache",
                "completed",
                str(audio),
                "legacy-tts",
                "voice-a",
                "legacy-voice-model",
                "wav",
            ),
        )
    AudioTimelineRepository(database).save(
        AudioTimeline.build(
            "episode",
            (
                TimelineItem.clip(
                    turn_id="turn",
                    host_id="host",
                    artifact_id="artifact",
                    duration_seconds=1.0,
                ),
            ),
        )
    )

    episode = episodes.get_episode("episode")
    run = runs.get("run")
    turns = HostTurnService(database).list_turns("episode")
    identity = HostTurnService(database).provider_identity("turn")
    artifact = TTSArtifactRepository(database).get_by_turn_id("turn")
    timeline = AudioTimelineRepository(database).get("episode")

    assert episode is not None and episode.title == "Legacy Episode"
    assert run is not None and run.state == "completed"
    assert len(turns) == 1 and turns[0].text == "legacy turn"
    assert identity is not None
    assert (identity.provider_id, identity.model) == ("legacy-provider", "legacy-model")
    assert artifact is not None
    assert artifact.status == TTS_ARTIFACT_STATUS_COMPLETE
    assert artifact.path == audio
    assert timeline is not None
    assert timeline.episode_id == "episode"
    assert timeline.items[0].turn_id == "turn"
