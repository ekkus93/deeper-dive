"""Persistence operations specific to editable episode configuration."""

from __future__ import annotations

from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord


class EpisodeConfigurationRepository:
    """Repository for updating episode metadata and ordered host membership atomically."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def update(
        self,
        episode: EpisodeRecord,
        host_ids: list[str],
        *,
        expected_config_json: str,
    ) -> None:
        with self.database.transaction(immediate=True) as db:
            for table in ("generation_runs", "conversation_states", "conversation_turns"):
                if (
                    db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,),
                    ).fetchone()
                    and db.execute(
                        f"SELECT 1 FROM {table} WHERE episode_id=? LIMIT 1",
                        (episode.id,),
                    ).fetchone()
                ):
                    raise ValueError(
                        "episode configuration is frozen after generation starts; "
                        "create a new episode"
                    )
            cursor = db.execute(
                """UPDATE episodes SET title=?,focus=?,audience=?,technical_depth=?,
                target_duration_seconds=?,style=?,state=?,config_json=?,modified_at=?
                WHERE id=? AND project_id=? AND config_json=? AND state='draft'""",
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
                    expected_config_json,
                ),
            )
            if cursor.rowcount != 1:
                current = db.execute(
                    "SELECT modified_at,state FROM episodes WHERE id=? AND project_id=?",
                    (episode.id, episode.project_id),
                ).fetchone()
                if current is None:
                    raise KeyError(episode.id)
                raise ValueError(
                    "episode configuration changed concurrently or is no longer editable; retry"
                )
            db.execute("DELETE FROM episode_hosts WHERE episode_id=?", (episode.id,))
            for ordinal, host_id in enumerate(host_ids):
                db.execute(
                    "INSERT INTO episode_hosts(episode_id,host_id,ordinal) VALUES (?,?,?)",
                    (episode.id, host_id, ordinal),
                )
            # A persisted plan is a snapshot of the episode configuration. Keeping it after
            # configuration changes would let show-plan/generate silently use stale hosts,
            # duration, focus, or provider overrides. Runs remain historical records, but a
            # new generation must rebuild the invalidated plan first.
            db.execute(
                """DELETE FROM segment_plans WHERE episode_plan_id IN
                (SELECT id FROM episode_plans WHERE episode_id=?)""",
                (episode.id,),
            )
            db.execute("DELETE FROM episode_plans WHERE episode_id=?", (episode.id,))
