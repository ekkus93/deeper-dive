"""Persistence operations specific to editable episode configuration."""

from __future__ import annotations

from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord


class EpisodeConfigurationRepository:
    """Repository for updating episode metadata and ordered host membership atomically."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def update(self, episode: EpisodeRecord, host_ids: list[str]) -> None:
        with self.database.transaction() as db:
            cursor = db.execute(
                """UPDATE episodes SET title=?,focus=?,audience=?,technical_depth=?,
                target_duration_seconds=?,style=?,state=?,config_json=?,modified_at=?
                WHERE id=? AND project_id=?""",
                (
                    episode.title,
                    episode.focus,
                    episode.audience,
                    episode.technical_depth,
                    episode.target_duration_seconds,
                    episode.style,
                    episode.state,
                    episode.config_json,
                    episode.modified_at,
                    episode.id,
                    episode.project_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(episode.id)
            db.execute("DELETE FROM episode_hosts WHERE episode_id=?", (episode.id,))
            for ordinal, host_id in enumerate(host_ids):
                db.execute(
                    "INSERT INTO episode_hosts(episode_id,host_id,ordinal) VALUES (?,?,?)",
                    (episode.id, host_id, ordinal),
                )
