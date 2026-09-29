from __future__ import annotations

import wave
from pathlib import Path

import deeper_dive.composition as composition_module
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.claim_verification import ClaimVerificationService
from deeper_dive.composition import ProductionComposition
from deeper_dive.conversation_state import ConversationStateRepository
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.material_claims import MaterialClaimService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository, HostProfileRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class UnusedTurnProvider:
    def generate_turn(self, decision: object) -> dict[str, object]:
        raise AssertionError("not used")


class UnusedVerifier:
    def classify(self, request: dict[str, object]) -> dict[str, object]:
        raise AssertionError("not used")


def _project_with_episode(tmp_path: Path) -> tuple[DeeperDiveService, str, str]:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Review")
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    hosts = HostEpisodeRepository(database)
    hosts.create_host(
        HostProfileRecord(
            "h1",
            project.id,
            "Host One",
            tts_provider="tts",
            tts_voice="voice-a",
        )
    )
    episode = EpisodeConfigurationService(database).create(
        project.id,
        EpisodeConfiguration(
            title="Episode One",
            focus="Focus",
            host_ids=("h1",),
        ),
    )
    HostTurnService(database, UnusedTurnProvider())
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("turn-1", episode.id, 0, 0, "h1", "Original turn", "[]"),
        )
    return service, project.id, episode.id


def _configure_fake_repair_provider(service: DeeperDiveService) -> None:
    UserConfigStore(service.workspaces.data_dir / "config.json").save(
        UserConfig(
            providers={
                "repair": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "tts": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={"host_generation": "repair:fake-v1"},
        )
    )


def _insert_repair_worthy_claim(database: Database, project_id: str, episode_id: str) -> None:
    MaterialClaimService(database)
    ClaimVerificationService(database, UnusedVerifier())
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO material_claims(
                id,project_id,episode_id,turn_id,text,span_start,span_end,created_at
            ) VALUES (?,?,?,?,?,?,?,?)""",
            ("claim-1", project_id, episode_id, "turn-1", "Original turn", 0, 13, "t"),
        )
        connection.execute(
            """INSERT INTO claim_verifications(
                claim_id,state,rationale,confidence,supporting_evidence_ids_json,
                contradicting_evidence_ids_json
            ) VALUES (?,?,?,?,?,?)""",
            (
                "claim-1",
                "contradicted",
                "Repair it",
                0.8,
                '["chunk-a"]',
                '["chunk-b"]',
            ),
        )


def test_regenerate_episode_audio_sanitizes_runtime_failure(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    service.workspaces.initialize()
    project = service.create_project("Failure Case")
    composition = ProductionComposition.build(service=service)

    def fail_stage(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("token=secret-value runtime exploded")

    monkeypatch.setattr(composition_module, "_tts_stage", fail_stage)

    try:
        composition.regenerate_episode_audio(project.id, "episode-1")
    except RuntimeError as error:
        message = str(error)
    else:
        raise AssertionError("expected audio regeneration failure")

    assert "episode audio regeneration failed:" in message
    assert "[REDACTED]" in message
    assert "secret-value" not in message


def test_controller_repair_regenerates_audio_timeline_and_review_export(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id = _project_with_episode(tmp_path)
    _configure_fake_repair_provider(service)
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    _insert_repair_worthy_claim(database, project_id, episode_id)
    output = service.workspaces.project_root(project_id) / "output"
    output.mkdir(parents=True, exist_ok=True)
    episode_audio = output / f"{episode_id}.wav"
    episode_audio.write_bytes(b"stale audio")
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
            ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                "turn-1",
                "artifact-1",
                "cache-1",
                "completed",
                str(episode_audio),
                "tts",
                "h1",
                "m",
            ),
        )

    app = DeeperDiveApp(service)
    app.current_project_id = project_id
    app.current_episode_id = episode_id
    controller = TranscriptReviewController()

    repaired = controller.repair_turn("turn-1", app)
    export_path = controller.export_markdown(app)

    assert repaired is not None
    assert repaired.text == "The repaired production turn is factually rechecked."
    with database.connection() as connection:
        claims = connection.execute(
            """SELECT mc.id,mc.text,cv.state,cv.rationale
            FROM material_claims mc JOIN claim_verifications cv ON cv.claim_id=mc.id
            WHERE mc.turn_id=?""",
            ("turn-1",),
        ).fetchall()
    assert len(claims) == 1
    assert str(claims[0]["id"]) != "claim-1"
    assert str(claims[0]["text"]) == repaired.text
    assert str(claims[0]["state"]) == "insufficient_evidence"
    assert "Configured fake claim verification marker." in str(claims[0]["rationale"])
    state = ConversationStateRepository(database).get(episode_id)
    assert state is not None
    assert repaired.text in state.running_summary
    assert state.recent_context_refs == ("turn-1",)
    assert export_path.is_file()
    exported = export_path.read_text(encoding="utf-8")
    assert "# Transcript review:" in exported
    assert repaired.text in exported
    assert episode_audio.exists()
    with wave.open(str(episode_audio), "rb") as wav:
        assert wav.getnframes() > 0
    timeline = AudioTimelineRepository(database).get(episode_id)
    assert timeline is not None
    assert timeline.placements[0].item.turn_id == "turn-1"
