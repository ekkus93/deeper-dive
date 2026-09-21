from __future__ import annotations

from types import SimpleNamespace

from deeper_dive.composition import ProductionComposition
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.transcript_review_screen import TranscriptReviewController


def test_transcript_audio_resolution_is_strictly_episode_specific(tmp_path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Audio isolation")
    output = composition.service.workspaces.project_root(project.id) / "output"
    output.mkdir(parents=True, exist_ok=True)
    episode_a = "episode-a"
    episode_b = "episode-b"
    audio_a = output / f"{episode_a}.mp3"
    audio_b = output / f"{episode_b}.wav"
    unrelated = output / "unrelated.mp3"
    audio_a.write_bytes(b"a")
    audio_b.write_bytes(b"b")
    unrelated.write_bytes(b"other")
    app = SimpleNamespace(
        service=composition.service,
        current_project_id=project.id,
        current_episode_id=episode_a,
    )
    controller = TranscriptReviewController(playback=composition.playback_controller)

    assert controller.audio_path(app) == audio_a

    app.current_episode_id = episode_b
    assert controller.audio_path(app) == audio_b

    app.current_episode_id = "episode-without-audio"
    assert controller.audio_path(app) is None
