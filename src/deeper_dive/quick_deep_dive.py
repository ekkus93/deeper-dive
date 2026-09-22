"""Quick Deep Dive workflow built on normal durable episode configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from deeper_dive.domain.clock import Clock, SystemClock
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.research_policy import ResearchMode, ResearchPolicy, ResearchPolicyStore
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository
from deeper_dive.user_config import UserConfigStore


@dataclass(frozen=True, slots=True)
class QuickDeepDiveDefaults:
    """Defaults for the one-click quick episode path."""

    title: str = "Quick Deep Dive"
    focus: str = "Create a focused deep dive from the indexed project corpus."
    target_duration_seconds: int = 1200
    research_mode: ResearchMode = ResearchMode.USEFUL
    fallback_presets: tuple[str, str] = ("curious_explainer", "skeptic")


class QuickDeepDiveService:
    """Create a normal draft episode using effective Quick Deep Dive defaults."""

    def __init__(
        self,
        database: Database,
        *,
        clock: Clock | None = None,
        defaults: QuickDeepDiveDefaults | None = None,
    ) -> None:
        self.database = database
        self.clock = SystemClock() if clock is None else clock
        self.defaults = defaults or QuickDeepDiveDefaults()
        self.hosts = HostEpisodeRepository(database)
        self.episodes = EpisodeConfigurationService(database, clock=self.clock)
        self.research_policies = ResearchPolicyStore(database)

    def create_episode(self, project_id: str) -> EpisodeRecord:
        """Create a normal durable draft episode and episode research override."""

        defaults = self._effective_defaults(project_id)
        host_ids = self._host_ids(project_id, defaults.fallback_presets)
        config = EpisodeConfiguration(
            title=defaults.title,
            focus=defaults.focus,
            audience="general",
            technical_depth="balanced",
            target_duration_seconds=defaults.target_duration_seconds,
            style="discussion",
            host_ids=host_ids,
            research_overrides={"policy": defaults.research_mode.value},
        )
        episode = self.episodes.create(project_id, config)
        self.research_policies.set_episode(
            episode.id,
            ResearchPolicy(mode=defaults.research_mode),
        )
        return episode

    def _effective_defaults(self, project_id: str) -> QuickDeepDiveDefaults:
        """Resolve built-in < user < project Quick Deep Dive defaults."""

        effective = self.defaults
        data_dir = self.database.path.parents[2]
        user = UserConfigStore(data_dir / "config.json").load().defaults
        effective = self._apply_overrides(effective, user)
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT instructions FROM projects WHERE id=?", (project_id,)
            ).fetchone()
        if row is None:
            raise KeyError(project_id)
        instructions = str(row["instructions"] or "").strip()
        if instructions:
            try:
                payload = json.loads(instructions)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                quick = payload.get("quick_deep_dive")
                if isinstance(quick, dict):
                    effective = self._apply_overrides(
                        effective,
                        {f"quick_deep_dive_{key}": str(value) for key, value in quick.items()},
                    )
        return effective

    @staticmethod
    def _apply_overrides(
        defaults: QuickDeepDiveDefaults, values: dict[str, str]
    ) -> QuickDeepDiveDefaults:
        duration = values.get("quick_deep_dive_duration_minutes", "").strip()
        presets = values.get("quick_deep_dive_host_presets", "").strip()
        research = values.get("quick_deep_dive_research_policy", "").strip()
        target_duration_seconds = defaults.target_duration_seconds
        fallback_presets = defaults.fallback_presets
        research_mode = defaults.research_mode
        if duration:
            minutes = int(duration)
            if minutes <= 0:
                raise ValueError("Quick Deep Dive duration must be positive")
            target_duration_seconds = minutes * 60
        if presets:
            parsed = tuple(item.strip() for item in presets.split(",") if item.strip())
            if len(parsed) != 2:
                raise ValueError("Quick Deep Dive requires exactly two host presets")
            fallback_presets = parsed
        if research:
            research_mode = ResearchMode(research)
        return replace(
            defaults,
            target_duration_seconds=target_duration_seconds,
            fallback_presets=fallback_presets,
            research_mode=research_mode,
        )

    def _host_ids(self, project_id: str, presets: tuple[str, str]) -> tuple[str, ...]:
        existing = self.hosts.list_hosts(project_id)
        if existing:
            return tuple(host.id for host in existing[:2])
        created: list[str] = []
        for preset in presets:
            host = create_host_from_preset(preset, project_id)
            self.hosts.create_host(host.to_record())
            created.append(host.id)
        return tuple(created)
