from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_playback import PlaybackState
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def test_episode_library_play_uses_selected_episode_audio_only(tmp_path: Path) -> None:
    asyncio.run(_episode_library_play_uses_selected_episode_audio_only(tmp_path))


async def _episode_library_play_uses_selected_episode_audio_only(tmp_path: Path) -> None:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 10, 8, 12, 30, tzinfo=UTC)),
    )
    project = service.create_project("Playback")
    first_episode, first_run = _episode_with_run(service, project.id, "First")
    second_episode, second_run = _episode_with_run(service, project.id, "Second")
    output = service.workspaces.project_root(project.id) / "output"
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{first_episode}.wav").write_bytes(b"first")
    selected_audio = output / f"{second_episode}.wav"
    selected_audio.write_bytes(b"second")

    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.action_navigate("library")
        await pilot.pause()
        screen = app.screen
        screen.selected_episode_id = second_episode
        screen.refresh_library()
        played: list[Path] = []

        def fake_play(audio_path: Path, *, start_seconds: float = 0.0) -> PlaybackState:
            played.append(audio_path)
            return PlaybackState(True, True, f"Playing {audio_path.name}", audio_path)

        with patch.object(app.composition.playback_controller, "play", side_effect=fake_play):
            screen.action_play_selected()

        assert played == [selected_audio]
        assert app.current_episode_id == second_episode
        assert app.current_run_id == second_run
        assert app.current_run_id != first_run


def _episode_with_run(
    service: DeeperDiveService,
    project_id: str,
    title: str,
) -> tuple[str, str]:
    now = format_timestamp(service.clock.now())
    episode_id = str(new_episode_id())
    service.hosts(project_id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project_id,
            title=title,
            created_at=now,
            modified_at=now,
        ),
        [],
    )
    run_id = str(new_run_id())
    service.runs(project_id).create(
        GenerationRunRecord(run_id, episode_id, "export", "completed", now, now)
    )
    return episode_id, run_id
