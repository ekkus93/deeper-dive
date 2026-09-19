from __future__ import annotations

import pytest

from deeper_dive.audio_timeline import AudioTimeline, AudioTimelineRepository, TimelineItem
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord


def test_timeline_duration_math_chapters_pauses_and_overlap_are_deterministic() -> None:
    timeline = AudioTimeline.build(
        "episode-1",
        (
            TimelineItem.clip(
                turn_id="turn-1",
                host_id="host-a",
                artifact_id="audio-1",
                duration_seconds=10.0,
                metadata={"chapter_title": "Opening"},
            ),
            TimelineItem.pause(1.5),
            TimelineItem.clip(
                turn_id="turn-2",
                host_id="host-b",
                artifact_id="audio-2",
                duration_seconds=8.0,
                overlap_previous_seconds=2.0,
                metadata={"chapter_title": "Counterpoint"},
            ),
        ),
    )

    assert timeline.duration_seconds == pytest.approx(17.5)
    assert [placement.start_seconds for placement in timeline.placements] == [0.0, 10.0, 9.5]
    assert [placement.end_seconds for placement in timeline.placements] == [10.0, 11.5, 17.5]
    assert [
        (chapter.title, chapter.start_seconds, chapter.turn_id) for chapter in timeline.chapters
    ] == [
        ("Opening", 0.0, "turn-1"),
        ("Counterpoint", 9.5, "turn-2"),
    ]


def test_timeline_validation_rejects_invalid_items() -> None:
    with pytest.raises(ValueError, match="turn_id and artifact_id"):
        TimelineItem.clip(turn_id="", host_id="h1", artifact_id="a1", duration_seconds=1.0)
    with pytest.raises(ValueError, match="overlap cannot exceed"):
        TimelineItem.clip(
            turn_id="t1",
            host_id="h1",
            artifact_id="a1",
            duration_seconds=1.0,
            overlap_previous_seconds=2.0,
        )
    with pytest.raises(ValueError, match="first timeline item cannot overlap"):
        AudioTimeline.build(
            "episode-1",
            (
                TimelineItem.clip(
                    turn_id="t1",
                    host_id="h1",
                    artifact_id="a1",
                    duration_seconds=1.0,
                    overlap_previous_seconds=0.5,
                ),
            ),
        )


def test_timeline_metadata_persists_and_round_trips(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = Database(tmp_path / "project.db")
    CorpusRepository(database).create_project(ProjectRecord("project-1", "Project", "now", "now"))
    HostEpisodeRepository(database).create_episode(
        EpisodeRecord("episode-1", "project-1", "Episode", "now", "now"), []
    )
    repository = AudioTimelineRepository(database)
    timeline = AudioTimeline.build(
        "episode-1",
        (
            TimelineItem.clip(
                turn_id="turn-1",
                host_id="host-a",
                artifact_id="audio-1",
                duration_seconds=2.25,
            ),
            TimelineItem.pause(0.75),
        ),
    )

    repository.save(timeline)
    restored = repository.get("episode-1")

    assert restored == timeline
    assert restored is not None
    assert restored.duration_seconds == pytest.approx(3.0)
    assert restored.chapters[0].title == "Turn 1"
