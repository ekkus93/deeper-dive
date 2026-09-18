"""Episode configuration use cases and reproducible configuration snapshots."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from deeper_dive.domain.clock import Clock, SystemClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_configuration import EpisodeConfigurationRepository
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository


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

    def snapshot(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


class EpisodeConfigurationService:
    """Create/edit independent episode configurations with immutable-at-write snapshots."""

    def __init__(self, database: Database, *, clock: Clock | None = None) -> None:
        self.database = database
        self.clock = SystemClock() if clock is None else clock
        self.episodes = HostEpisodeRepository(database)
        self.configuration = EpisodeConfigurationRepository(database)

    def create(self, project_id: str, config: EpisodeConfiguration) -> EpisodeRecord:
        self._validate_hosts(project_id, config)
        timestamp = format_timestamp(self.clock.now())
        record = self._record(str(new_episode_id()), project_id, timestamp, timestamp, config)
        self.episodes.create_episode(record, list(config.host_ids))
        return record

    def edit(self, episode_id: str, config: EpisodeConfiguration) -> EpisodeRecord:
        existing = self.episodes.get_episode(episode_id)
        if existing is None:
            raise KeyError(episode_id)
        self._validate_hosts(existing.project_id, config)
        record = self._record(
            existing.id,
            existing.project_id,
            existing.created_at,
            format_timestamp(self.clock.now()),
            config,
        )
        self.configuration.update(record, list(config.host_ids))
        return record

    def load_configuration(self, episode_id: str) -> EpisodeConfiguration:
        record = self.episodes.get_episode(episode_id)
        if record is None:
            raise KeyError(episode_id)
        payload = json.loads(record.config_json)
        return EpisodeConfiguration(
            title=record.title,
            focus=record.focus,
            audience=record.audience,
            technical_depth=record.technical_depth,
            target_duration_seconds=record.target_duration_seconds,
            style=record.style,
            host_ids=tuple(self.episodes.list_episode_host_ids(record.id)),
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
                raise ValueError(f"host {host_id!r} does not belong to project")

    @staticmethod
    def _record(
        episode_id: str,
        project_id: str,
        created_at: str,
        modified_at: str,
        config: EpisodeConfiguration,
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
            state="draft",
            config_json=json.dumps(snapshot, sort_keys=True),
            created_at=created_at,
            modified_at=modified_at,
        )
