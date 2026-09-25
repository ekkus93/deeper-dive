from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.provider_factory import ProviderConfigurationError, ProviderFactory
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts_generation import TTSArtifactRepository, TTS_ARTIFACT_STATUS_COMPLETE
from deeper_dive.user_config import UserConfigStore


def test_existing_concrete_provider_config_records_load_with_new_defaults(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {
                    "planner": {
                        "provider_type": "fake",
                        "default_model": "fake-v1",
                    },
                    "speech": {
                        "provider_type": "fake-tts",
                    },
                },
                "defaults": {
                    "episode_planning": "planner:fake-v1",
                    "host_generation": "planner:fake-v1",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = UserConfigStore(config_path).load()
    planner = loaded.providers["planner"]
    speech = loaded.providers["speech"]

    assert planner.timeout_seconds == 60.0
    assert planner.response_format == "wav"
    assert planner.voices == ()
    assert planner.credential_env is None
    assert speech.timeout_seconds == 60.0
    assert speech.response_format == "wav"

    providers = ProviderFactory(environ={}).build(loaded)
    assert providers.llm_registry.get("planner").models()[0].model == "fake-v1"
    assert providers.tts_registry.get("speech").voices()[0].id == "voice-a"


@pytest.mark.parametrize("provider_type", ["llm", "tts"])
def test_ambiguous_legacy_provider_types_fail_with_guidance(
    tmp_path: Path,
    provider_type: str,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {
                    "legacy": {
                        "provider_type": provider_type,
                        "default_model": "legacy-model",
                    }
                },
                "defaults": {},
            }
        ),
        encoding="utf-8",
    )

    config = UserConfigStore(config_path).load()
    with pytest.raises(
        ProviderConfigurationError,
        match="legacy generic provider_type .* ambiguous; choose a concrete adapter type",
    ):
        ProviderFactory(environ={}).build(config)


def test_existing_episode_run_transcript_and_tts_artifacts_load(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)),
    )
    project = service.create_project("Legacy persisted workspace")
    timestamp = format_timestamp(service.clock.now())
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    host_record = host.to_record()
    episode = EpisodeRecord(
        id="legacy-episode",
        project_id=project.id,
        title="Legacy episode",
        focus="Load persisted artifacts",
        target_duration_seconds=60,
        created_at=timestamp,
        modified_at=timestamp,
    )
    run = GenerationRunRecord(
        id="legacy-run",
        episode_id=episode.id,
        stage="export",
        state="completed",
        created_at=timestamp,
        modified_at=timestamp,
    )
    repository = service.hosts(project.id)
    repository.create_host(host_record)
    repository.create_episode(episode, [host.id])
    service.runs(project.id).create(run)

    project_root = service.workspaces.project_root(project.id)
    artifact_path = project_root / "output" / "tts" / "legacy.wav"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"RIFF legacy fake wav")
    database = Database(project_root / "project.db")
    HostTurnService(database)
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                "legacy-turn",
                episode.id,
                0,
                0,
                host.id,
                "Legacy transcript turn with persisted evidence.",
                json.dumps(["source-chunk-1"]),
            ),
        )
        connection.execute(
            """INSERT INTO conversation_turn_provider_identity(
                turn_id,provider_id,model
            ) VALUES (?,?,?)""",
            ("legacy-turn", "planner", "fake-v1"),
        )
        connection.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                "legacy-turn",
                "legacy-artifact",
                "legacy-cache-key",
                "completed",
                str(artifact_path),
                "speech",
                "voice-a",
                "fake-v1",
            ),
        )

    loaded_episode = repository.get_episode(episode.id)
    loaded_run = service.runs(project.id).latest_for_episode(episode.id)
    turns = HostTurnService(database).list_turns(episode.id)
    identity = HostTurnService(database).provider_identity("legacy-turn")
    artifact = TTSArtifactRepository(database).get_by_cache_key("legacy-cache-key")

    assert loaded_episode is not None
    assert loaded_episode.title == "Legacy episode"
    assert loaded_run == run
    assert len(turns) == 1
    assert turns[0].text == "Legacy transcript turn with persisted evidence."
    assert turns[0].evidence_ids == ("source-chunk-1",)
    assert identity is not None
    assert identity.provider_id == "planner"
    assert identity.model == "fake-v1"
    assert artifact is not None
    assert artifact.status == TTS_ARTIFACT_STATUS_COMPLETE
    assert artifact.path == artifact_path
    assert artifact.path.read_bytes().startswith(b"RIFF")

    with database.connection() as connection:
        stored_status = connection.execute(
            "SELECT status FROM tts_artifacts WHERE turn_id=?",
            ("legacy-turn",),
        ).fetchone()["status"]
    assert stored_status == TTS_ARTIFACT_STATUS_COMPLETE
