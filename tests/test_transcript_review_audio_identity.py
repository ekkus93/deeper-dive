from pathlib import Path
from types import SimpleNamespace

from deeper_dive.transcript_review_screen import TranscriptReviewController


class _Workspaces:
    def __init__(self, root: Path) -> None:
        self.root = root

    def project_root(self, project_id: str) -> Path:
        assert project_id == "project-1"
        return self.root


def _app(root: Path, episode_id: str) -> object:
    service = SimpleNamespace(workspaces=_Workspaces(root))
    return SimpleNamespace(
        service=service,
        current_project_id="project-1",
        current_episode_id=episode_id,
    )


def test_audio_path_never_falls_back_to_another_episode(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    episode_b = output / "episode-b.mp3"
    episode_b.write_bytes(b"episode-b")

    controller = TranscriptReviewController()

    assert controller.audio_path(_app(tmp_path, "episode-a")) is None  # type: ignore[arg-type]
    assert controller.audio_path(_app(tmp_path, "episode-b")) == episode_b  # type: ignore[arg-type]


def test_audio_path_prefers_selected_episode_identity(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    episode_a = output / "episode-a.wav"
    episode_b = output / "episode-b.mp3"
    episode_a.write_bytes(b"episode-a")
    episode_b.write_bytes(b"episode-b")

    controller = TranscriptReviewController()

    assert controller.audio_path(_app(tmp_path, "episode-a")) == episode_a  # type: ignore[arg-type]
    assert controller.audio_path(_app(tmp_path, "episode-b")) == episode_b  # type: ignore[arg-type]
