from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.provider_factory import ProviderConfigurationError, ProviderFactory
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts_generation import TTS_ARTIFACT_STATUS_COMPLETE, TTSArtifactRepository
from deeper_dive.user_config import UserConfigStore


def test_existing_minimal_provider_configuration_records_still_load(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    config_path = data_dir / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {
                    "planner": {"provider_type": "fake", "default_model": "fake-v1"},
                    "speech": {"provider_type": "fake-tts"},
                },
                "defaults": {"host_generation": "planner:fake-v1"},
            }
        ),
        encoding="utf-8",
    )

    config = UserConfigStore(config_path).load()
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )

    assert config.providers["planner"].timeout_seconds == 60.0
    assert config.providers["planner"].response_format == "wav"
    assert config.providers["speech"].voices == ()
    assert "planner" in composition.provider_controller.llm_registry.provider_ids()
    assert "speech" in composition.providers.tts_registry.provider_ids()


def test_existing_episode_run_transcript_and_audio_artifacts_still_load(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    _write_provider_config(data_dir)
    service = DeeperDiveService(WorkspaceManager(data_dir))
    service.workspaces.initialize()
    project = service.create_project("Compatibility")
    service.add_pasted_source(project.id, "Source", "Existing persisted source text.")
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    service.hosts(project.id).create_host(host.to_record())
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episode = EpisodeConfigurationService(database).create(
        project.id,
        EpisodeConfiguration(
            title="Compatibility episode",
            focus="Load existing persisted data",
            target_duration_seconds=60,
            host_ids=(host.id,),
        ),
    )
    HostTurnService(database)
    root = service.workspaces.project_root(project.id)
    legacy_audio = root / "output" / "tts" / "legacy-artifact.wav"
    legacy_audio.parent.mkdir(parents=True, exist_ok=True)
    legacy_audio.write_bytes(b"legacy provider audio")
    episode_audio = root / "output" / f"{episode.id}.wav"
    episode_audio.write_bytes(b"legacy composed audio")
    run = GenerationRunRecord("run-existing", episode.id, "export", "completed", "t", "t")
    GenerationRunRepository(database).create(run)

    with database.transaction() as db:
        db.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("turn-existing", episode.id, 0, 0, host.id, "existing transcript", "[]"),
        )
        db.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                "turn-existing",
                "legacy-artifact",
                "legacy-key",
                "completed",
                str(legacy_audio),
                "speech",
                "voice-a",
                None,
            ),
        )

    reloaded = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    reloaded_db = reloaded.database_for_project(project.id)
    loaded_episode = reloaded.service.hosts(project.id).get_episode(episode.id)
    loaded_run = reloaded.generation_run_repository(project.id).get(run.id)
    loaded_turns = HostTurnService(reloaded_db).list_turns(episode.id)
    artifact = TTSArtifactRepository(reloaded_db).get_by_cache_key("legacy-key")

    assert loaded_episode is not None
    assert loaded_episode.title == "Compatibility episode"
    assert loaded_run is not None
    assert loaded_run.state == "completed"
    assert [turn.text for turn in loaded_turns] == ["existing transcript"]
    assert artifact is not None
    assert artifact.status == TTS_ARTIFACT_STATUS_COMPLETE
    assert artifact.path.read_bytes() == b"legacy provider audio"


def test_ambiguous_legacy_provider_entries_fail_with_actionable_guidance(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {"legacy": {"provider_type": "llm"}},
                "defaults": {},
            }
        ),
        encoding="utf-8",
    )
    config = UserConfigStore(config_path).load()

    with pytest.raises(ProviderConfigurationError, match="choose a concrete adapter type"):
        ProviderFactory(environ={}).build(config)


def _write_provider_config(data_dir: Path) -> None:
    UserConfigStore(data_dir / "config.json").save(
        {
            "schema_version": 1,
            "providers": {
                "planner": {"provider_type": "fake", "default_model": "fake-v1"},
                "speech": {"provider_type": "fake-tts"},
            },
            "defaults": {"host_generation": "planner:fake-v1"},
        }  # type: ignore[arg-type]
    )
