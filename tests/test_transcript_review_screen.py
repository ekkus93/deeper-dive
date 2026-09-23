from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.claim_verification import ClaimVerificationService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.material_claims import MaterialClaimService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    HostEpisodeRepository,
    HostProfileRecord,
)
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import (
    TranscriptReviewController,
    TranscriptReviewScreen,
)
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
    hosts.create_host(HostProfileRecord("h1", project.id, "Host One"))
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


def test_transcript_review_resolves_audio_by_selected_episode_identity(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id = _project_with_episode(tmp_path)
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    other = EpisodeConfigurationService(database).create(
        project_id,
        EpisodeConfiguration(title="Episode Two", focus="Other", host_ids=("h1",)),
    )
    output = service.workspaces.project_root(project_id) / "output"
    output.mkdir(parents=True, exist_ok=True)
    expected = output / f"{episode_id}.wav"
    wrong = output / f"{other.id}.wav"
    expected.write_bytes(b"episode-one")
    wrong.write_bytes(b"episode-two")
    app = DeeperDiveApp(service)
    app.current_project_id = project_id
    app.current_episode_id = episode_id

    assert TranscriptReviewController().audio_path(app) == expected

    app.current_episode_id = other.id
    assert TranscriptReviewController().audio_path(app) == wrong

    expected.unlink()
    app.current_episode_id = episode_id
    assert TranscriptReviewController().audio_path(app) is None


def test_transcript_review_screen_repair_uses_injected_repair_callback(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_repair_screen(tmp_path))


async def _exercise_repair_screen(tmp_path: Path) -> None:
    service, project_id, episode_id = _project_with_episode(tmp_path)
    repaired: list[str] = []

    def repair(turn_id: str) -> None:
        repaired.append(turn_id)
        database = Database(service.workspaces.project_root(project_id) / "project.db")
        with database.transaction() as connection:
            connection.execute(
                "UPDATE conversation_turns SET text=? WHERE id=?",
                ("Repaired turn", turn_id),
            )

    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project_id
        app.current_episode_id = episode_id
        await app.push_screen(TranscriptReviewScreen(TranscriptReviewController(repair=repair)))
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TranscriptReviewScreen)
        screen.action_regenerate_turn()
        await pilot.pause()
        assert repaired == ["turn-1"]
        transcript = screen.query_one("#transcript-turn", Static)
        assert "Repaired turn" in str(transcript.render())


def test_transcript_review_default_repair_uses_production_service(
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

    repaired = TranscriptReviewController().repair_turn("turn-1", app)

    with database.connection() as connection:
        turn = connection.execute(
            "SELECT text,evidence_ids_json FROM conversation_turns WHERE id=?",
            ("turn-1",),
        ).fetchone()
        stale_claim = connection.execute(
            "SELECT 1 FROM material_claims WHERE id=?", ("claim-1",)
        ).fetchone()
        stale_audio = connection.execute(
            "SELECT 1 FROM tts_artifacts WHERE turn_id=?", ("turn-1",)
        ).fetchone()
    assert repaired is not None
    assert turn is not None
    assert "segments" in str(turn["text"])
    assert turn["evidence_ids_json"] == '["chunk-a", "chunk-b"]'
    assert stale_claim is None
    assert stale_audio is None
    assert not episode_audio.exists()


def test_transcript_review_section_repair_uses_production_service(tmp_path: Path) -> None:
    service, project_id, episode_id = _project_with_episode(tmp_path)
    _configure_fake_repair_provider(service)
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    _insert_repair_worthy_claim(database, project_id, episode_id)
    app = DeeperDiveApp(service)
    app.current_project_id = project_id
    app.current_episode_id = episode_id

    repaired = TranscriptReviewController().repair_section(app, 0)

    assert [turn.id for turn in repaired] == ["turn-1"]
    with database.connection() as connection:
        turn = connection.execute("SELECT text FROM conversation_turns WHERE id=?", ("turn-1",)).fetchone()
    assert turn is not None
    assert "segments" in str(turn["text"])


def test_transcript_review_repair_without_provider_is_actionable(tmp_path: Path) -> None:
    service, project_id, episode_id = _project_with_episode(tmp_path)
    app = DeeperDiveApp(service)
    app.current_project_id = project_id
    app.current_episode_id = episode_id

    try:
        TranscriptReviewController().repair_turn("turn-1", app)
    except RuntimeError as error:
        assert "no configured LLM provider" in str(error)
    else:
        raise AssertionError("expected missing provider to be actionable")
