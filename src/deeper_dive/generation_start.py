"""Durable, duplicate-safe generation run creation and readiness gating."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.generation_roles import GenerationRoleContext, required_generation_model_roles
from deeper_dive.hosts import HostProfile
from deeper_dive.model_roles import ModelRole, ModelRoleAssignments
from deeper_dive.network_scope import ProviderNetworkPolicy
from deeper_dive.plan_validity import conversation_work_remains, evaluate_episode_plan
from deeper_dive.preflight import (
    PreflightEstimate,
    PreflightIssue,
    PreflightReport,
)
from deeper_dive.source_readiness import source_index_ready
from deeper_dive.storage.episode_repositories import HostEpisodeRepository, HostProfileRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord

if TYPE_CHECKING:
    from deeper_dive.composition import ProductionComposition

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

    def __init__(
        self, composition: ProductionComposition, *, ffmpeg_executable: Path | None = None
    ) -> None:
        self.composition = composition
        self.ffmpeg_executable = ffmpeg_executable

    def preflight(self, project_id: str, episode_id: str) -> PreflightReport:
        service = self.composition.service
        repository = service.hosts(project_id)
        episode = repository.get_episode(episode_id)
        if episode is None or episode.project_id != project_id:
            return PreflightReport(
                (PreflightIssue("episode_missing", f"episode not found: {episode_id}"),),
                PreflightEstimate(0, 0, 0, None),
            )
        database = self.composition.database_for_project(project_id)
        sources = [source for source in service.list_sources(project_id) if source.included]
        indexed_source_count = sum(
            1
            for source in sources
            if source_index_ready(source, len(service.list_source_chunks(project_id, source.id)))
        )
        host_records = self._episode_hosts(repository, project_id, episode_id)
        hosts = tuple(HostProfile.from_record(host) for host in host_records)
        (
            assignments,
            assignment_errors,
        ) = self.composition.effective_model_role_assignments_for_episode(
            project_id,
            episode_id,
        )
        config = EpisodeConfigurationService(database).load_configuration(episode_id)
        target_seconds = episode.target_duration_seconds or config.target_duration_seconds
        target_minutes = target_seconds / 60 if target_seconds > 0 else 20.0
        report: PreflightReport = self.composition.preflight_service.check(
            assignments=assignments,
            hosts=hosts,
            source_count=len(sources),
            indexed_source_count=indexed_source_count,
            target_minutes=target_minutes,
            ffmpeg_executable=self.ffmpeg_executable,
            local_provider_ids=self._local_provider_ids(),
            local_only=self._local_only(),
            required_model_roles=self._required_model_roles(
                repository,
                episode_id,
                assignments,
            ),
            tts_response_formats=self._tts_response_formats(),
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

        # Capture the revision first: preflight describes this exact configuration.
        episode = self.composition.service.hosts(project_id).get_episode(episode_id)
        revision = None if episode is None else episode.config_json
        report = self.preflight(project_id, episode_id)
        report.require_ready()
        result = select_or_create_generation_run(
            self.composition.service,
            project_id,
            episode_id,
            expected_episode_config_json=revision,
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
        assignments: ModelRoleAssignments,
    ) -> tuple[ModelRole, ...]:
        validity = evaluate_episode_plan(repository.database, episode_id)
        work_remains = (not validity.usable) or conversation_work_remains(
            repository.database,
            episode_id,
        )
        return required_generation_model_roles(
            GenerationRoleContext(
                valid_plan_exists=validity.usable,
                conversation_work_remains=work_remains,
                assignments=assignments,
            )
        )

    def _local_provider_ids(self) -> frozenset[str]:
        return ProviderNetworkPolicy.local_provider_ids(
            self.composition.provider_controller.config()
        )

    def _local_only(self) -> bool:
        config = self.composition.provider_controller.config()
        return ProviderNetworkPolicy.local_only(config.defaults)

    def _tts_response_formats(self) -> dict[str, str]:
        config = self.composition.provider_controller.config()
        return {
            provider_id: provider_config.response_format
            for provider_id, provider_config in config.providers.items()
        }


def select_or_create_generation_run(
    service: DeeperDiveService,
    project_id: str,
    episode_id: str,
    *,
    expected_episode_config_json: str | None = None,
) -> GenerationStartResult:
    """Return the active episode run or durably create one pending run.

    Repeated Generate actions are idempotent while a run remains active. Terminal
    runs do not block a later explicit generation attempt from creating a new run.
    Selection and insertion are one ``BEGIN IMMEDIATE`` transaction; pass the
    episode revision observed at preflight to refuse a start after an edit.
    """

    now = format_timestamp(service.clock.now())
    candidate = GenerationRunRecord(
        id=str(new_run_id()),
        episode_id=episode_id,
        stage="sources",
        state="pending",
        created_at=now,
        modified_at=now,
    )
    run, created = service.runs(project_id).select_or_create(
        candidate,
        active_states=_ACTIVE_STATES,
        terminal_states=_TERMINAL_STATES,
        expected_episode_config_json=expected_episode_config_json,
        project_id=project_id,
    )
    return GenerationStartResult(run, created)
