from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController


def test_audio_resolution_never_crosses_episode_identity(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Audio isolation")
    output = service.workspaces.project_root(project.id) / "output"
    output.mkdir(parents=True)
    episode_a = "episode-a"
    episode_b = "episode-b"
    audio_a = output / f"{episode_a}.wav"
    audio_b = output / f"{episode_b}.mp3"
    unrelated = output / "some-other-export.wav"
    audio_a.write_bytes(b"a")
    audio_b.write_bytes(b"b")
    unrelated.write_bytes(b"unrelated")
    controller = TranscriptReviewController()
    app = SimpleNamespace(
        service=service,
        current_project_id=project.id,
        current_episode_id=episode_a,
    )

    assert controller.audio_path(app) == audio_a
    app.current_episode_id = episode_b
    assert controller.audio_path(app) == audio_b

    audio_b.unlink()
    assert controller.audio_path(app) is None
    assert controller.audio_path(app) != audio_a
    assert controller.audio_path(app) != unrelated
