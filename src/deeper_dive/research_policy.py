"""Persistent project/episode supplemental-research policy."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from deeper_dive.storage.database import Database


class ResearchMode(StrEnum):
    OFF = "off"
    CONSERVATIVE = "conservative"
    USEFUL = "useful"
    AGGRESSIVE = "aggressive"


@dataclass(frozen=True, slots=True)
class ResearchControls:
    find_newer_research: bool = True
    contradictory_evidence: bool = True
    missing_citations: bool = True
    prefer_primary_sources: bool = True
    replication_review_evidence: bool = True
    background_context: bool = True
    permit_general_interest: bool = False


@dataclass(frozen=True, slots=True)
class ResearchPolicy:
    mode: ResearchMode = ResearchMode.USEFUL
    controls: ResearchControls = field(default_factory=ResearchControls)

    @property
    def automated_search_allowed(self) -> bool:
        return self.mode is not ResearchMode.OFF


class ResearchPolicyStore:
    """Store project defaults and sparse episode overrides in the project database."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._ensure_schema()

    def set_project(self, project_id: str, policy: ResearchPolicy) -> None:
        self._put("project", project_id, policy)

    def set_episode(self, episode_id: str, policy: ResearchPolicy | None) -> None:
        if policy is None:
            with self.database.transaction() as connection:
                connection.execute(
                    "DELETE FROM research_policies WHERE scope='episode' AND scope_id=?",
                    (episode_id,),
                )
            return
        self._put("episode", episode_id, policy)

    def project(self, project_id: str) -> ResearchPolicy:
        return self._get("project", project_id) or ResearchPolicy()

    def episode(self, project_id: str, episode_id: str) -> ResearchPolicy:
        return self._get("episode", episode_id) or self.project(project_id)

    def _put(self, scope: str, scope_id: str, policy: ResearchPolicy) -> None:
        payload = json.dumps(asdict(policy.controls), sort_keys=True)
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO research_policies(scope, scope_id, mode, controls_json)
                VALUES(?,?,?,?)
                ON CONFLICT(scope, scope_id) DO UPDATE SET
                    mode=excluded.mode, controls_json=excluded.controls_json""",
                (scope, scope_id, policy.mode.value, payload),
            )

    def _get(self, scope: str, scope_id: str) -> ResearchPolicy | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT mode, controls_json FROM research_policies WHERE scope=? AND scope_id=?",
                (scope, scope_id),
            ).fetchone()
        if row is None:
            return None
        controls = ResearchControls(**json.loads(str(row["controls_json"])))
        return ResearchPolicy(ResearchMode(str(row["mode"])), controls)

    def _ensure_schema(self) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS research_policies (
                    scope TEXT NOT NULL CHECK(scope IN ('project','episode')),
                    scope_id TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('off','conservative','useful','aggressive')),
                    controls_json TEXT NOT NULL,
                    PRIMARY KEY(scope, scope_id)
                )"""
            )
