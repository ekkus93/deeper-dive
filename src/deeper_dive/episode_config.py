"""Episode configuration use cases and reproducible configuration snapshots."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from deeper_dive.domain.clock import Clock, SystemClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_configuration import EpisodeConfigurationRepository
from deeper_dive.storage.episode_errors import (
    EpisodeConfigurationConflict,
    EpisodeConfigurationError,
    EpisodeFrozenError,
)
from deeper_dive.storage.episode_plan_repository import EpisodePlanRepository
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository

__all__ = [
    "EpisodeConfiguration",
    "EpisodeConfigurationConflict",
    "EpisodeConfigurationError",
    "EpisodeConfigurationService",
    "EpisodeFrozenError",
]


@dataclass(frozen=True, slots=True)
class EpisodeConfiguration:
    title: str
    focus: str = ""
    audience: str = "general"
    technical_depth: str = "balanced"
    target_duration_seconds: int = 1800
    style: str = "discussion"
    host_ids: tuple[str, ...] = ()
    must_cover: tuple[str, ...] = ()
    avoid_topics: tuple[str, ...] = ()
    source_overrides: dict[str, bool] = field(default_factory=dict)
    research_overrides: dict[str, Any] = field(default_factory=dict)
    model_overrides: dict[str, dict[str, str]] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.title.strip():
            raise ValueError("episode title must not be empty")
        if self.target_duration_seconds <= 0:
            raise ValueError("target duration must be positive")
        if len(set(self.host_ids)) != len(self.host_ids):
            raise ValueError("episode host order cannot contain duplicate hosts")

    def normalized(self) -> EpisodeConfiguration:
        """Canonical form used for storage and comparison on every surface.

        Text is stripped, host/list fields become tuples of stripped non-blank
        entries, durations are integers, and ``None``/blank research override
        values are dropped (unset and empty mean the same thing).
        """

        return replace(
            self,
            title=self.title.strip(),
            focus=self.focus.strip(),
            audience=self.audience.strip(),
            technical_depth=self.technical_depth.strip(),
            style=self.style.strip(),
            target_duration_seconds=int(self.target_duration_seconds),
            host_ids=tuple(item.strip() for item in self.host_ids),
            must_cover=tuple(item.strip() for item in self.must_cover if item.strip()),
            avoid_topics=tuple(item.strip() for item in self.avoid_topics if item.strip()),
            research_overrides={
                key: value
                for key, value in self.research_overrides.items()
                if value is not None and not (isinstance(value, str) and not value.strip())
            },
        )

    def snapshot(self) -> dict[str, Any]:
        normalized = self.normalized()
        normalized.validate()
        return asdict(normalized)


class EpisodeConfigurationService:
    """Create/edit independent episode configurations with immutable-at-write snapshots."""

    def __init__(self, database: Database, *, clock: Clock | None = None) -> None:
        self.database = database
        self.clock = SystemClock() if clock is None else clock
        self.episodes = HostEpisodeRepository(database)
        self.configuration = EpisodeConfigurationRepository(database)

    def create(self, project_id: str, config: EpisodeConfiguration) -> EpisodeRecord:
        config = config.normalized()
        self._validate_hosts(project_id, config)
        timestamp = format_timestamp(self.clock.now())
        record = self._record(str(new_episode_id()), project_id, timestamp, timestamp, config)
        self.episodes.create_episode(record, list(config.host_ids))
        return record

    def edit(
        self,
        episode_id: str,
        config: EpisodeConfiguration,
        *,
        expected_revision: str | None = None,
    ) -> EpisodeRecord:
        """Edit a draft episode.

        ``expected_revision`` is the revision (``EpisodeRecord.config_json``) the
        caller's form was loaded from. It is enforced by the update's
        compare-and-swap, so an edit that lands after the caller's own pre-checks
        still raises ``EpisodeConfigurationConflict`` instead of being overwritten.
        """

        config = config.normalized()
        existing = self.episodes.get_episode(episode_id)
        if existing is None:
            raise KeyError("episode not found")
        if expected_revision is not None and existing.config_json != expected_revision:
            raise EpisodeConfigurationConflict(
                "episode configuration changed since it was loaded; reload and retry"
            )
        self._validate_hosts(existing.project_id, config)
        current = self.load_configuration(episode_id)
        if current.snapshot() == config.snapshot():
            return existing
        if existing.state != "draft":
            raise EpisodeFrozenError(
                "episode configuration is frozen after generation starts; create a new episode"
            )
        EpisodePlanRepository(self.database).require_configuration_editable(episode_id)
        record = self._record(
            existing.id,
            existing.project_id,
            existing.created_at,
            format_timestamp(self.clock.now()),
            config,
            state=existing.state,
        )
        self.configuration.update(
            record,
            list(config.host_ids),
            expected_config_json=(
                existing.config_json if expected_revision is None else expected_revision
            ),
        )
        return record

    def load_with_revision(self, episode_id: str) -> tuple[EpisodeConfiguration, str]:
        """Return the configuration and the revision it was derived from (one read)."""

        record = self.episodes.get_episode(episode_id)
        if record is None:
            raise KeyError("episode not found")
        return self.configuration_from_record(record), record.config_json

    def load_configuration(self, episode_id: str) -> EpisodeConfiguration:
        record = self.episodes.get_episode(episode_id)
        if record is None:
            raise KeyError("episode not found")
        return self.configuration_from_record(record)

    def configuration_from_record(self, record: EpisodeRecord) -> EpisodeConfiguration:
        """Derive the configuration from one episode row (its revision is ``config_json``).

        Host order comes from the same snapshot, so config and revision cannot
        disagree even if an edit lands after the row was read.
        """

        payload = json.loads(record.config_json)
        if "host_ids" in payload:
            host_ids = tuple(payload["host_ids"])
        else:
            host_ids = tuple(self.episodes.list_episode_host_ids(record.id))
        return EpisodeConfiguration(
            title=record.title,
            focus=record.focus,
            audience=record.audience,
            technical_depth=record.technical_depth,
            target_duration_seconds=record.target_duration_seconds,
            style=record.style,
            host_ids=host_ids,
            must_cover=tuple(payload.get("must_cover", ())),
            avoid_topics=tuple(payload.get("avoid_topics", ())),
            source_overrides=dict(payload.get("source_overrides", {})),
            research_overrides=dict(payload.get("research_overrides", {})),
            model_overrides=dict(payload.get("model_overrides", {})),
        )

    def _validate_hosts(self, project_id: str, config: EpisodeConfiguration) -> None:
        config.validate()
        for host_id in config.host_ids:
            host = self.episodes.get_host(host_id)
            if host is None or host.project_id != project_id:
                raise ValueError("episode host does not belong to project")

    @staticmethod
    def _record(
        episode_id: str,
        project_id: str,
        created_at: str,
        modified_at: str,
        config: EpisodeConfiguration,
        *,
        state: str = "draft",
    ) -> EpisodeRecord:
        snapshot = config.snapshot()
        return EpisodeRecord(
            id=episode_id,
            project_id=project_id,
            title=config.title,
            focus=config.focus,
            audience=config.audience,
            technical_depth=config.technical_depth,
            target_duration_seconds=config.target_duration_seconds,
            style=config.style,
            state=state,
            config_json=json.dumps(snapshot, sort_keys=True),
            created_at=created_at,
            modified_at=modified_at,
        )
