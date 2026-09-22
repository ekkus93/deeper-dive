from __future__ import annotations

import asyncio
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.host_turn import HostTurnService
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


class UnusedTurnProvider:
    def generate_turn(self, decision: object) -> dict[str, object]:
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
        assert "Repaired turn" in screen.query_one("#transcript-turn").renderable
