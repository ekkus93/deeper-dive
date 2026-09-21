"""Production dependency composition for Deeper Dive surfaces."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeper_dive.application.events import ProgressSink
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_playback import AudioPlaybackBackend, AudioPlaybackController
from deeper_dive.episode_planner import EpisodePlanGenerator, EpisodePlannerService
from deeper_dive.export import EpisodeExporter
from deeper_dive.generation_monitor import GenerationMonitorController
from deeper_dive.llm import LLMMessage, LLMProvider, LLMRequest
from deeper_dive.pipeline import DEFAULT_STAGES, PipelineContext, PipelineOrchestrator, StageHandler
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderBuildResult, ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.research_controller import PersistentResearchController
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRepository
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.targeted_repair import (
    RepairRechecker,
    SummaryUpdater,
    TargetedRepairService,
    TurnRepairProvider,
)
from deeper_dive.tts_benchmark import TTSBenchmarkService
from deeper_dive.user_config import UserConfigStore


@dataclass(frozen=True, slots=True)
class LLMEpisodePlanGenerator:
    """Adapt the normalized LLM boundary to structured episode planning."""

    provider: LLMProvider
    model: str | None = None

    def generate_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        response = self.provider.generate(
            LLMRequest(
                messages=(
                    LLMMessage(
                        "system",
                        "Return a JSON episode plan with a non-empty segments array.",
                    ),
                    LLMMessage("user", json.dumps(request, sort_keys=True)),
                ),
                model=self.model,
                response_schema={"type": "object", "required": ["segments"]},
            )
        )
        payload: object = response.structured
        if payload is None:
            payload = json.loads(response.text)
        if not isinstance(payload, Mapping):
            raise ValueError("planning provider returned a non-object response")
        return dict(payload)


@dataclass(slots=True)
class ProductionComposition:
    """Application-wide services constructed through one production path."""

    service: DeeperDiveService
    config_store: UserConfigStore
    providers: ProviderBuildResult
    provider_controller: ProviderController
    research_controller: PersistentResearchController
    preflight_controller: PreflightController
    generation_monitor_controller: GenerationMonitorController
    benchmark_service: TTSBenchmarkService
    playback_controller: AudioPlaybackController

    @classmethod
    def build(
        cls,
        data_dir: Path | None = None,
        *,
        service: DeeperDiveService | None = None,
        provider_factory: ProviderFactory | None = None,
        playback_backend: AudioPlaybackBackend | None = None,
    ) -> ProductionComposition:
        app_service = service or DeeperDiveService(WorkspaceManager(data_dir))
        app_service.workspaces.initialize()
        config_store = UserConfigStore(app_service.workspaces.data_dir / "config.json")
        factory = provider_factory or ProviderFactory()
        providers = factory.build(config_store.load())
        provider_controller = ProviderController(
            config_store,
            providers.llm_registry,
            providers.tts_providers,
            provider_factory=factory,
        )
        research_controller = PersistentResearchController(
            lambda project_id: (app_service.workspaces.project_root(project_id) / "project.db")
        )
        monitor_controller = GenerationMonitorController(
            runner=lambda run_id, progress: cls._run_generation_pipeline(
                app_service,
                run_id,
                progress,
            )
        )
        composition = cls(
            service=app_service,
            config_store=config_store,
            providers=providers,
            provider_controller=provider_controller,
            research_controller=research_controller,
            preflight_controller=PreflightController(),
            generation_monitor_controller=monitor_controller,
            benchmark_service=TTSBenchmarkService(),
            playback_controller=AudioPlaybackController(playback_backend),
        )
        app_service._production_composition = composition  # type: ignore[attr-defined]
        return composition

    def database_for_project(self, project_id: str) -> Database:
        """Return the production database boundary for one project workspace."""

        return Database(self.service.workspaces.project_root(project_id) / "project.db")

    def planning_service(
        self, project_id: str, generator: EpisodePlanGenerator
    ) -> EpisodePlannerService:
        """Construct the shared planner while keeping its provider boundary injectable."""

        return EpisodePlannerService(self.database_for_project(project_id), generator)

    def configured_planning_service(
        self, project_id: str, provider_id: str, model: str | None = None
    ) -> EpisodePlannerService:
        """Construct planning from the same configured provider registry used in production."""

        provider = self.providers.llm_registry.get(provider_id)
        return self.planning_service(project_id, LLMEpisodePlanGenerator(provider, model))

    def pipeline_service(
        self,
        project_id: str,
        handlers: Mapping[str, StageHandler],
        *,
        progress: ProgressSink | None = None,
    ) -> PipelineOrchestrator:
        """Construct durable orchestration with injectable idempotent stage handlers."""

        repository = GenerationRunRepository(self.database_for_project(project_id))
        return PipelineOrchestrator(repository, handlers, progress=progress)

    def exporter(self, project_id: str) -> EpisodeExporter:
        """Construct the exporter rooted in the selected project workspace."""

        output_dir = self.service.workspaces.project_root(project_id) / "exports"
        return EpisodeExporter(output_dir)

    def targeted_repair_service(
        self,
        project_id: str,
        provider: TurnRepairProvider,
        rechecker: RepairRechecker,
        summary_updater: SummaryUpdater,
    ) -> TargetedRepairService:
        """Construct transcript repair while preserving injectable provider boundaries."""

        return TargetedRepairService(
            self.database_for_project(project_id), provider, rechecker, summary_updater
        )

    @staticmethod
    def _run_generation_pipeline(
        service: DeeperDiveService,
        run_id: str,
        progress: ProgressSink,
    ) -> None:
        project_id = _project_id_for_run(service, run_id)
        repository = service.runs(project_id)
        PipelineOrchestrator(
            repository,
            _production_stage_handlers(),
            progress=progress,
        ).run(run_id)


def _project_id_for_run(service: DeeperDiveService, run_id: str) -> str:
    for project in service.list_projects():
        if service.runs(project.id).get(run_id) is not None:
            return project.id
    raise KeyError(f"unknown generation run: {run_id}")


def _production_stage_handlers() -> dict[str, StageHandler]:
    return {stage: _durable_stage_boundary for stage in DEFAULT_STAGES}


def _durable_stage_boundary(context: PipelineContext) -> None:
    """Production-safe stage boundary until richer stage services own the work.

    The orchestrator still owns durable state transitions, retries, checkpoints,
    pause/cancel boundaries, and progress events. Stage-specific content generation
    can replace these handlers incrementally without changing TUI/CLI wiring.
    """

    _ = context
