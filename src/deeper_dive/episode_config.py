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
    InvalidModelOverrides,
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


def _normalized_source_overrides(value: object) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise ValueError("source overrides must be a mapping")
    result: dict[str, bool] = {}
    for key, flag in value.items():
        if not isinstance(key, str) or not isinstance(flag, bool):
            raise ValueError("source overrides must map source ids to true or false")
        result[key.strip()] = flag
    return result


def _normalized_model_overrides(value: object) -> dict[str, dict[str, str]]:
    """Canonical ``{role: {"provider": ..., "model": ...}}``.

    ``model_roles`` also accepts the ``"provider:model"`` string form, which older
    writers and imports can store, so it is accepted here and canonicalized to the
    mapping form. Shapes nothing can use raise a ``ValueError`` naming the role.
    """

    if not isinstance(value, dict):
        raise InvalidModelOverrides("model overrides must be a mapping")
    result: dict[str, dict[str, str]] = {}
    for role, assignment in value.items():
        if not isinstance(role, str):
            raise InvalidModelOverrides("model override roles must be text")
        if isinstance(assignment, str):
            provider, separator, model = assignment.partition(":")
            if not separator:
                raise InvalidModelOverrides(
                    f"model override {role} must be provider:model or provider/model settings"
                )
            result[role.strip()] = {"provider": provider.strip(), "model": model.strip()}
            continue
        if not isinstance(assignment, dict):
            raise InvalidModelOverrides(
                f"model override {role} must be provider:model or provider/model settings"
            )
        cleaned: dict[str, str] = {}
        for key, item in assignment.items():
            if not isinstance(key, str) or not isinstance(item, str):
                raise InvalidModelOverrides(f"model override {role} settings must be text")
            cleaned[key.strip()] = item.strip()
        result[role.strip()] = cleaned
    return result


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

        for name in ("title", "focus", "audience", "technical_depth", "style"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"episode {name} must be text")
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
            source_overrides=_normalized_source_overrides(self.source_overrides),
            research_overrides={
                str(key).strip(): value.strip() if isinstance(value, str) else value
                for key, value in self.research_overrides.items()
                if value is not None and not (isinstance(value, str) and not value.strip())
            },
            # Whitespace only: a blank override value stays blank so the shared
            # model-role validation can still reject it visibly.
            model_overrides=_normalized_model_overrides(self.model_overrides),
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
        # Compare against the row already read: a second read could see a newer
        # revision than the ``existing`` record this method returns.
        try:
            unchanged = self.configuration_from_record(existing).snapshot() == config.snapshot()
        except ValueError:
            # A stored value that no longer normalizes (for example a malformed
            # model override) must not make the episode uneditable: the edit that
            # replaces it is by definition a change.
            unchanged = False
        if unchanged:
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

    def load_configuration(
        self, episode_id: str, *, drop_invalid_model_overrides: bool = False
    ) -> EpisodeConfiguration:
        record = self.episodes.get_episode(episode_id)
        if record is None:
            raise KeyError("episode not found")
        return self.configuration_from_record(
            record, drop_invalid_model_overrides=drop_invalid_model_overrides
        )

    def configuration_from_record(
        self, record: EpisodeRecord, *, drop_invalid_model_overrides: bool = False
    ) -> EpisodeConfiguration:
        """Derive the configuration from one episode row (its revision is ``config_json``).

        A stored ``null`` for ``model_overrides`` means "none". Any other non-mapping
        value raises ``InvalidModelOverrides`` unless ``drop_invalid_model_overrides``
        is set (the repair path: ``episode configure --clear-model-overrides``).

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
            model_overrides=self._stored_model_overrides(
                payload.get("model_overrides"), drop_invalid_model_overrides
            ),
        )

    @staticmethod
    def _stored_model_overrides(value: object, drop_invalid: bool) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        if drop_invalid:
            return {}
        raise InvalidModelOverrides("stored model overrides must be a mapping")

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
