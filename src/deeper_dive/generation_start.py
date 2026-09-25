# ruff: noqa: I001
"""Durable, duplicate-safe generation run creation and readiness gating."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deeper_dive.domain.clock import format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.hosts import HostProfile
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight import (
    PreflightEstimate,
    PreflightIssue,
    PreflightReport,
)
from deeper_dive.storage.episode_repositories import HostEpisodeRepository, HostProfileRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord


_ACTIVE_STATES = frozenset({"pending", "running", "paused"})
_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class GenerationStartResult:
    """The durable run selected for a Generate action."""

    run: GenerationRunRecord
    created: bool
    preflight: PreflightReport | None = None


class GenerationStartService:
    """Shared CLI/TUI generation-start policy and preflight boundary."""

    def __init__(self, composition: object, *, ffmpeg_executable: Path | None = None) -> None:
        self.composition = composition
        self.ffmpeg_executable = ffmpeg_executable

    def preflight(self, project_id: str, episode_id: str) -> PreflightReport:
        service = self.composition.service  # type: ignore[attr-defined]
        repository = service.hosts(project_id)
        episode = repository.get_episode(episode_id)
        if episode is None or episode.project_id != project_id:
            return PreflightReport(
                (PreflightIssue("episode_missing", f"episode not found: {episode_id}"),),
                PreflightEstimate(0, 0, 0, None),
            )
        database = self.composition.database_for_project(project_id)  # type: ignore[attr-defined]
        sources = [source for source in service.list_sources(project_id) if source.included]
        indexed_source_count = sum(
            1 for source in sources if service.list_source_chunks(project_id, source.id)
        )
        host_records = self._episode_hosts(repository, project_id, episode_id)
        hosts = tuple(HostProfile.from_record(host) for host in host_records)
        (
            assignments,
            assignment_errors,
        ) = self.composition.effective_model_role_assignments_for_episode(  # type: ignore[attr-defined]
            project_id,
            episode_id,
        )
        config = EpisodeConfigurationService(database).load_configuration(episode_id)
        target_seconds = episode.target_duration_seconds or config.target_duration_seconds
        target_minutes = target_seconds / 60 if target_seconds > 0 else 20.0
        report: PreflightReport = self.composition.preflight_service.check(  # type: ignore[attr-defined]
            assignments=assignments,
            hosts=hosts,
            source_count=len(sources),
            indexed_source_count=indexed_source_count,
            target_minutes=target_minutes,
            ffmpeg_executable=self.ffmpeg_executable,
            local_provider_ids=self._local_provider_ids(),
            local_only=self._local_only(),
            required_model_roles=self._required_model_roles(repository, episode_id),
        )
        if assignment_errors:
            report = PreflightReport(
                (
                    *(PreflightIssue("llm_assignment", error) for error in assignment_errors),
                    *report.issues,
                ),
                report.estimate,
                report.routes,
            )
        return report

    def start(self, project_id: str, episode_id: str) -> GenerationStartResult:
        """Preflight and select the duplicate-safe durable run for generation."""

        report = self.preflight(project_id, episode_id)
        report.require_ready()
        result = select_or_create_generation_run(
            self.composition.service,  # type: ignore[attr-defined]
            project_id,
            episode_id,
        )
        return GenerationStartResult(result.run, result.created, report)

    def _episode_hosts(
        self,
        repository: HostEpisodeRepository,
        project_id: str,
        episode_id: str,
    ) -> tuple[HostProfileRecord, ...]:
        host_ids = repository.list_episode_host_ids(episode_id)
        hosts_by_id = {host.id: host for host in repository.list_hosts(project_id)}
        return tuple(hosts_by_id[host_id] for host_id in host_ids if host_id in hosts_by_id)

    def _required_model_roles(
        self,
        repository: HostEpisodeRepository,
        episode_id: str,
    ) -> tuple[ModelRole, ...]:
        roles = [ModelRole.HOST_GENERATION]
        if repository.get_plan(episode_id) is None:
            roles.insert(0, ModelRole.EPISODE_PLANNING)
        return tuple(roles)

    def _local_provider_ids(self) -> frozenset[str]:
        config = self.composition.provider_controller.config()  # type: ignore[attr-defined]
        local_ids = {
            value.strip()
            for value in config.defaults.get("local_provider_ids", "").split(",")
            if value.strip()
        }
        local_types = {"fake", "fake-tts", "kitten", "llama-server", "local", "ollama"}
        for name, provider in config.providers.items():
            if getattr(provider, "provider_type", None) in local_types:
                local_ids.add(name)
        return frozenset(local_ids)

    def _local_only(self) -> bool:
        config = self.composition.provider_controller.config()  # type: ignore[attr-defined]
        value = config.defaults.get("local_only", "")
        return value.strip().lower() in {"1", "true", "yes", "on"}


def select_or_create_generation_run(
    service: object,
    project_id: str,
    episode_id: str,
) -> GenerationStartResult:
    """Return the active episode run or durably create one pending run.

    Repeated Generate actions are idempotent while a run remains active. Terminal
    runs do not block a later explicit generation attempt from creating a new run.
    """

    repository = service.runs(project_id)  # type: ignore[attr-defined]
    latest = repository.latest_for_episode(episode_id)
    if latest is not None and latest.state in _ACTIVE_STATES and not latest.cancel_requested:
        return GenerationStartResult(latest, False)
    if latest is not None and latest.state not in _TERMINAL_STATES | _ACTIVE_STATES:
        raise ValueError(f"cannot start generation from unsupported run state: {latest.state}")

    now = format_timestamp(service.clock.now())  # type: ignore[attr-defined]
    run = GenerationRunRecord(
        id=str(new_run_id()),
        episode_id=episode_id,
        stage="sources",
        state="pending",
        created_at=now,
        modified_at=now,
    )
    repository.create(run)
    return GenerationStartResult(run, True)
