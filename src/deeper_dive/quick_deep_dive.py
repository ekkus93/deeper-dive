"""Quick Deep Dive workflow built on normal durable episode configuration."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.domain.clock import Clock, SystemClock
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.research_policy import ResearchMode, ResearchPolicy, ResearchPolicyStore
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository


@dataclass(frozen=True, slots=True)
class QuickDeepDiveDefaults:
    """Defaults for the one-click quick episode path."""

    title: str = "Quick Deep Dive"
    focus: str = "Create a focused deep dive from the indexed project corpus."
    target_duration_seconds: int = 1200
    research_mode: ResearchMode = ResearchMode.USEFUL
    fallback_presets: tuple[str, str] = ("curious_explainer", "skeptic")


class QuickDeepDiveService:
    """Create a normal draft episode using defaults, without bypassing preflight/generation."""

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

        host_ids = self._host_ids(project_id)
        config = EpisodeConfiguration(
            title=self.defaults.title,
            focus=self.defaults.focus,
            audience="general",
            technical_depth="balanced",
            target_duration_seconds=self.defaults.target_duration_seconds,
            style="discussion",
            host_ids=host_ids,
            research_overrides={"policy": self.defaults.research_mode.value},
        )
        episode = self.episodes.create(project_id, config)
        self.research_policies.set_episode(
            episode.id,
            ResearchPolicy(mode=self.defaults.research_mode),
        )
        return episode

    def _host_ids(self, project_id: str) -> tuple[str, ...]:
        existing = self.hosts.list_hosts(project_id)
        if existing:
            return tuple(host.id for host in existing[:2])
        created: list[str] = []
        for preset in self.defaults.fallback_presets:
            host = create_host_from_preset(preset, project_id)
            self.hosts.create_host(host.to_record())
            created.append(host.id)
        return tuple(created)
