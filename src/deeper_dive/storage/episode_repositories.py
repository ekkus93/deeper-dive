"""Persistence records and repository operations for hosts and episodes."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class HostProfileRecord:
    id: str
    project_id: str
    display_name: str
    preset_origin: str | None = None
    role: str = ""
    expertise: str = ""
    instructions: str = ""
    behavior_json: str = "{}"
    evidence_priorities_json: str = "[]"
    tts_provider: str | None = None
    tts_voice: str | None = None


@dataclass(frozen=True, slots=True)
class HostRelationshipRecord:
    project_id: str
    from_host_id: str
    to_host_id: str
    relationship_json: str = "{}"


@dataclass(frozen=True, slots=True)
class EpisodeRecord:
    id: str
    project_id: str
    title: str
    created_at: str
    modified_at: str
    focus: str = ""
    audience: str = ""
    technical_depth: str = ""
    target_duration_seconds: int = 0
    style: str = ""
    state: str = "draft"
    config_json: str = "{}"


@dataclass(frozen=True, slots=True)
class EpisodePlanRecord:
    id: str
    episode_id: str
    created_at: str
    modified_at: str
    status: str = "draft"
    plan_json: str = "{}"


@dataclass(frozen=True, slots=True)
class SegmentPlanRecord:
    id: str
    episode_plan_id: str
    ordinal: int
    title: str
    purpose: str = ""
    target_duration_seconds: int = 0
    segment_json: str = "{}"


class HostEpisodeRepository:
    """Repository boundary for hosts, relationships, episodes, and plans."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def create_host(self, host: HostProfileRecord) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO hosts(
                    id,project_id,display_name,preset_origin,role,expertise,instructions,
                    behavior_json,evidence_priorities_json,tts_provider,tts_voice
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    host.id,
                    host.project_id,
                    host.display_name,
                    host.preset_origin,
                    host.role,
                    host.expertise,
                    host.instructions,
                    host.behavior_json,
                    host.evidence_priorities_json,
                    host.tts_provider,
                    host.tts_voice,
                ),
            )

    def get_host(self, host_id: str) -> HostProfileRecord | None:
        with self.database.connection() as db:
            row = db.execute("SELECT * FROM hosts WHERE id=?", (host_id,)).fetchone()
        return None if row is None else HostProfileRecord(**dict(row))

    def list_hosts(self, project_id: str) -> list[HostProfileRecord]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM hosts WHERE project_id=? ORDER BY display_name,id",
                (project_id,),
            ).fetchall()
        return [HostProfileRecord(**dict(row)) for row in rows]

    def upsert_relationship(self, relationship: HostRelationshipRecord) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO host_relationships(
                    project_id,from_host_id,to_host_id,relationship_json
                ) VALUES (?,?,?,?)
                ON CONFLICT(from_host_id,to_host_id)
                DO UPDATE SET project_id=excluded.project_id,
                    relationship_json=excluded.relationship_json""",
                (
                    relationship.project_id,
                    relationship.from_host_id,
                    relationship.to_host_id,
                    relationship.relationship_json,
                ),
            )

    def list_relationships(self, project_id: str) -> list[HostRelationshipRecord]:
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT project_id,from_host_id,to_host_id,relationship_json
                FROM host_relationships WHERE project_id=? ORDER BY from_host_id,to_host_id""",
                (project_id,),
            ).fetchall()
        return [HostRelationshipRecord(**dict(row)) for row in rows]

    def create_episode(self, episode: EpisodeRecord, host_ids: list[str]) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO episodes(
                    id,project_id,title,focus,audience,technical_depth,target_duration_seconds,
                    style,state,config_json,created_at,modified_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    episode.id,
                    episode.project_id,
                    episode.title,
                    episode.focus,
                    episode.audience,
                    episode.technical_depth,
                    episode.target_duration_seconds,
                    episode.style,
                    episode.state,
                    episode.config_json,
                    episode.created_at,
                    episode.modified_at,
                ),
            )
            for ordinal, host_id in enumerate(host_ids):
                db.execute(
                    "INSERT INTO episode_hosts(episode_id,host_id,ordinal) VALUES (?,?,?)",
                    (episode.id, host_id, ordinal),
                )

    def get_episode(self, episode_id: str) -> EpisodeRecord | None:
        with self.database.connection() as db:
            row = db.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
        return None if row is None else EpisodeRecord(**dict(row))

    def list_episodes(self, project_id: str) -> list[EpisodeRecord]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM episodes WHERE project_id=? ORDER BY created_at,id",
                (project_id,),
            ).fetchall()
        return [EpisodeRecord(**dict(row)) for row in rows]

    def list_episode_host_ids(self, episode_id: str) -> list[str]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT host_id FROM episode_hosts WHERE episode_id=? ORDER BY ordinal",
                (episode_id,),
            ).fetchall()
        return [str(row["host_id"]) for row in rows]

    def save_plan(self, plan: EpisodePlanRecord, segments: list[SegmentPlanRecord]) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO episode_plans(
                    id,episode_id,status,plan_json,created_at,modified_at
                ) VALUES (?,?,?,?,?,?)""",
                (
                    plan.id,
                    plan.episode_id,
                    plan.status,
                    plan.plan_json,
                    plan.created_at,
                    plan.modified_at,
                ),
            )
            for segment in segments:
                db.execute(
                    """INSERT INTO segment_plans(
                        id,episode_plan_id,ordinal,title,purpose,target_duration_seconds,segment_json
                    ) VALUES (?,?,?,?,?,?,?)""",
                    (
                        segment.id,
                        segment.episode_plan_id,
                        segment.ordinal,
                        segment.title,
                        segment.purpose,
                        segment.target_duration_seconds,
                        segment.segment_json,
                    ),
                )

    def get_plan(self, episode_id: str) -> EpisodePlanRecord | None:
        with self.database.connection() as db:
            row = db.execute(
                "SELECT * FROM episode_plans WHERE episode_id=?", (episode_id,)
            ).fetchone()
        return None if row is None else EpisodePlanRecord(**dict(row))

    def list_segments(self, episode_plan_id: str) -> list[SegmentPlanRecord]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM segment_plans WHERE episode_plan_id=? ORDER BY ordinal",
                (episode_plan_id,),
            ).fetchall()
        return [SegmentPlanRecord(**dict(row)) for row in rows]
