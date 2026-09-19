"""Deterministic audio timeline model and persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal

from deeper_dive.storage.database import Database

TimelineItemKind = Literal["clip", "pause"]


@dataclass(frozen=True, slots=True)
class TimelineItem:
    """One ordered audio clip or pause in an episode timeline."""

    kind: TimelineItemKind
    duration_seconds: float
    turn_id: str | None = None
    host_id: str | None = None
    artifact_id: str | None = None
    overlap_previous_seconds: float = 0.0
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.duration_seconds < 0:
            raise ValueError("timeline item duration must be non-negative")
        if self.overlap_previous_seconds < 0:
            raise ValueError("overlap_previous_seconds must be non-negative")
        if self.overlap_previous_seconds > self.duration_seconds:
            raise ValueError("overlap cannot exceed item duration")
        if self.kind == "clip" and (not self.turn_id or not self.artifact_id):
            raise ValueError("clip timeline items require turn_id and artifact_id")
        if self.kind == "pause" and self.turn_id is not None:
            raise ValueError("pause timeline items must not carry turn_id")

    @classmethod
    def clip(
        cls,
        *,
        turn_id: str,
        host_id: str,
        artifact_id: str,
        duration_seconds: float,
        overlap_previous_seconds: float = 0.0,
        metadata: dict[str, str] | None = None,
    ) -> TimelineItem:
        return cls(
            kind="clip",
            duration_seconds=duration_seconds,
            turn_id=turn_id,
            host_id=host_id,
            artifact_id=artifact_id,
            overlap_previous_seconds=overlap_previous_seconds,
            metadata=metadata or {},
        )

    @classmethod
    def pause(cls, duration_seconds: float, *, metadata: dict[str, str] | None = None) -> TimelineItem:
        return cls(kind="pause", duration_seconds=duration_seconds, metadata=metadata or {})


@dataclass(frozen=True, slots=True)
class TimelinePlacement:
    """Resolved placement of one timeline item."""

    item: TimelineItem
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True, slots=True)
class ChapterTimestamp:
    """Chapter timestamp derived from timeline turn order."""

    title: str
    start_seconds: float
    turn_id: str | None = None
    host_id: str | None = None


@dataclass(frozen=True, slots=True)
class AudioTimeline:
    """Resolved ordered timeline metadata for composition and export."""

    episode_id: str
    items: tuple[TimelineItem, ...]
    placements: tuple[TimelinePlacement, ...]
    chapters: tuple[ChapterTimestamp, ...]
    duration_seconds: float

    @classmethod
    def build(cls, episode_id: str, items: tuple[TimelineItem, ...]) -> AudioTimeline:
        if not episode_id:
            raise ValueError("episode_id must not be empty")
        placements: list[TimelinePlacement] = []
        chapters: list[ChapterTimestamp] = []
        cursor = 0.0
        for index, item in enumerate(items):
            start = max(0.0, cursor - item.overlap_previous_seconds)
            end = start + item.duration_seconds
            placements.append(TimelinePlacement(item, start, end))
            if item.kind == "clip":
                chapters.append(
                    ChapterTimestamp(
                        title=item.metadata.get("chapter_title") or f"Turn {len(chapters) + 1}",
                        start_seconds=start,
                        turn_id=item.turn_id,
                        host_id=item.host_id,
                    )
                )
            cursor = max(cursor, end)
            if index == 0 and item.overlap_previous_seconds:
                raise ValueError("first timeline item cannot overlap previous audio")
        return cls(
            episode_id=episode_id,
            items=items,
            placements=tuple(placements),
            chapters=tuple(chapters),
            duration_seconds=cursor,
        )

    def to_json(self) -> str:
        payload = {
            "episode_id": self.episode_id,
            "items": [asdict(item) for item in self.items],
            "placements": [
                {
                    "item_index": index,
                    "start_seconds": placement.start_seconds,
                    "end_seconds": placement.end_seconds,
                }
                for index, placement in enumerate(self.placements)
            ],
            "chapters": [asdict(chapter) for chapter in self.chapters],
            "duration_seconds": self.duration_seconds,
        }
        return json.dumps(payload, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> AudioTimeline:
        raw = json.loads(payload)
        items = tuple(TimelineItem(**item) for item in raw["items"])
        rebuilt = cls.build(str(raw["episode_id"]), items)
        if abs(rebuilt.duration_seconds - float(raw["duration_seconds"])) > 1e-9:
            raise ValueError("persisted timeline duration does not match rebuilt duration")
        return rebuilt


class AudioTimelineRepository:
    """Persistence boundary for durable audio timeline metadata."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def save(self, timeline: AudioTimeline) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO audio_timelines(episode_id,timeline_json,duration_seconds)
                VALUES (?,?,?)
                ON CONFLICT(episode_id) DO UPDATE SET
                    timeline_json=excluded.timeline_json,
                    duration_seconds=excluded.duration_seconds""",
                (timeline.episode_id, timeline.to_json(), timeline.duration_seconds),
            )

    def get(self, episode_id: str) -> AudioTimeline | None:
        with self.database.connection() as db:
            row = db.execute(
                "SELECT timeline_json FROM audio_timelines WHERE episode_id=?", (episode_id,)
            ).fetchone()
        if row is None:
            return None
        return AudioTimeline.from_json(str(row["timeline_json"]))
