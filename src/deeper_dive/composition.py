"""Production dependency composition for Deeper Dive surfaces."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeper_dive import model_roles
from deeper_dive.application.events import ProgressSink
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_playback import AudioPlaybackBackend, AudioPlaybackController
from deeper_dive.audio_timeline import AudioTimeline, AudioTimelineRepository, TimelineItem
from deeper_dive.director_decision import DirectorDecision
from deeper_dive.domain.clock import SystemClock, format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlanGenerator, EpisodePlannerService
from deeper_dive.export import EpisodeExporter
from deeper_dive.generation_monitor import GenerationMonitorController
from deeper_dive.host_turn import HostTurn, HostTurnService
from deeper_dive.host_turn_llm import LLMHostTurnProvider
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import LLMMessage, LLMProvider, LLMRequest
from deeper_dive.pipeline import (
    DEFAULT_STAGES,
    PipelineContext,
    PipelineOrchestrator,
    PipelineResult,
    StageHandler,
)
from deeper_dive.preflight import PreflightService
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderBuildResult, ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.research_controller import PersistentResearchController
from deeper_dive.research_execution import execute_research_gaps
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.targeted_repair import (
    RepairRechecker,
    SummaryUpdater,
    TargetedRepairService,
    TurnRepairProvider,
)
from deeper_dive.tts_benchmark import TTSBenchmarkService
from deeper_dive.tts_generation import (
    TTSArtifact,
    TTSArtifactRepository,
    TTSGenerationStage,
    TTSTurn,
)
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
    preflight_service: PreflightService
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
            lambda project_id: (app_service.workspaces.project_root(project_id) / "project.db"),
            research_callback=lambda project_id, gap_ids: execute_research_gaps(
                app_service,
                project_id,
                gap_ids,
            ),
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
            preflight_service=PreflightService(
                providers.llm_registry,
                providers.tts_registry,
            ),
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

        provider = self.provider_controller.llm_registry.get(provider_id)
        return self.planning_service(project_id, LLMEpisodePlanGenerator(provider, model))

    def effective_model_role_assignments(
        self,
        project_id: str,
        *,
        episode_overrides: Mapping[str, Any] | None = None,
    ) -> tuple[model_roles.ModelRoleAssignments, tuple[str, ...]]:
        """Resolve provider/model roles through production configuration precedence."""

        project = self.service.open_project(project_id)
        project_defaults = (
            model_roles.project_model_defaults_from_instructions(project.instructions)
            if project is not None
            else {}
        )
        return model_roles.effective_model_role_assignments(
            user_defaults=self.provider_controller.config().defaults,
            project_defaults=project_defaults,
            episode_overrides=episode_overrides or {},
        )

    def effective_model_role_assignments_for_episode(
        self,
        project_id: str,
        episode_id: str,
    ) -> tuple[model_roles.ModelRoleAssignments, tuple[str, ...]]:
        """Resolve model roles for one durable episode using episode > project > user order."""

        config = EpisodeConfigurationService(
            self.database_for_project(project_id)
        ).load_configuration(episode_id)
        return self.effective_model_role_assignments(
            project_id,
            episode_overrides=config.model_overrides,
        )

    def effective_model_role_assignments_for_run(
        self,
        project_id: str,
        run_id: str,
    ) -> tuple[model_roles.ModelRoleAssignments, tuple[str, ...]]:
        """Resolve model roles for the durable episode attached to a generation run."""

        run = self.generation_run_repository(project_id).get(run_id)
        if run is None:
            raise KeyError(f"unknown generation run: {run_id}")
        return self.effective_model_role_assignments_for_episode(project_id, run.episode_id)

    def generation_run_repository(self, project_id: str) -> GenerationRunRepository:
        """Construct the production run-state repository for one project."""

        return GenerationRunRepository(self.database_for_project(project_id))

    def create_generation_run(self, project_id: str, episode_id: str) -> GenerationRunRecord:
        """Create a durable pending generation run through the production composition path."""

        timestamp = format_timestamp(SystemClock().now())
        run = GenerationRunRecord(
            id=str(new_run_id()),
            episode_id=episode_id,
            stage=DEFAULT_STAGES[0],
            state="pending",
            created_at=timestamp,
            modified_at=timestamp,
        )
        self.generation_run_repository(project_id).create(run)
        return run

    def pipeline_service(
        self,
        project_id: str,
        handlers: Mapping[str, StageHandler],
        *,
        progress: ProgressSink | None = None,
    ) -> PipelineOrchestrator:
        """Construct durable orchestration with injectable idempotent stage handlers."""

        return PipelineOrchestrator(
            self.generation_run_repository(project_id),
            handlers,
            progress=progress,
        )

    def generation_pipeline(
        self,
        project_id: str,
        *,
        progress: ProgressSink | None = None,
        handlers: Mapping[str, StageHandler] | None = None,
    ) -> PipelineOrchestrator:
        """Construct the production generation pipeline for one project."""

        return self.pipeline_service(
            project_id,
            handlers or _production_stage_handlers(self.service, project_id),
            progress=progress,
        )

    def run_generation(
        self,
        project_id: str,
        run_id: str,
        *,
        progress: ProgressSink | None = None,
    ) -> PipelineResult:
        """Execute a production-composed generation run to a terminal/control state."""

        _assignments, errors = self.effective_model_role_assignments_for_run(project_id, run_id)
        if errors:
            raise ValueError("invalid model-role configuration: " + "; ".join(errors))
        return self.generation_pipeline(project_id, progress=progress).run(run_id)

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
            _production_stage_handlers(service, project_id),
            progress=progress,
        ).run(run_id)


def _project_id_for_run(service: DeeperDiveService, run_id: str) -> str:
    for project in service.list_projects():
        if service.runs(project.id).get(run_id) is not None:
            return project.id
    raise KeyError(f"unknown generation run: {run_id}")


def _production_stage_handlers(
    service: DeeperDiveService,
    project_id: str,
) -> dict[str, StageHandler]:
    handlers = {stage: _durable_stage_boundary for stage in DEFAULT_STAGES}
    handlers["planning"] = lambda context: _planning_stage(service, project_id, context)
    handlers["conversation"] = lambda context: _conversation_stage(service, project_id, context)
    handlers["tts"] = lambda context: _tts_stage(service, project_id, context)
    handlers["composition"] = lambda context: _composition_stage(service, project_id, context)
    return handlers


def _planning_stage(
    service: DeeperDiveService,
    project_id: str,
    context: PipelineContext,
) -> None:
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    if HostEpisodeRepository(database).get_plan(context.episode_id) is not None:
        return
    composition = getattr(service, "_production_composition", None)
    if composition is None:
        raise RuntimeError("production composition is unavailable for episode planning")
    assignments, errors = composition.effective_model_role_assignments_for_episode(
        project_id,
        context.episode_id,
    )
    if errors:
        raise ValueError("invalid model-role configuration: " + "; ".join(errors))
    assignment = assignments.resolve(model_roles.ModelRole.EPISODE_PLANNING)
    if assignment is None:
        raise ValueError("no provider/model assignment for episode_planning")
    planner = composition.configured_planning_service(
        project_id,
        assignment.provider,
        assignment.model,
    )
    planner.build_plan(context.episode_id)


def _conversation_stage(
    service: DeeperDiveService,
    project_id: str,
    context: PipelineContext,
) -> None:
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    existing_turns = HostTurnService(database)
    if existing_turns.list_turns(context.episode_id):
        return
    repository = HostEpisodeRepository(database)
    host_ids = tuple(repository.list_episode_host_ids(context.episode_id))
    if not host_ids:
        return
    episode = repository.get_episode(context.episode_id)
    if episode is None:
        raise KeyError(context.episode_id)
    composition = getattr(service, "_production_composition", None)
    if composition is None:
        raise RuntimeError("production composition is unavailable for conversation generation")
    assignments, errors = composition.effective_model_role_assignments_for_episode(
        project_id, context.episode_id
    )
    if errors:
        raise ValueError("invalid model-role configuration: " + "; ".join(errors))
    assignment = assignments.resolve(model_roles.ModelRole.HOST_GENERATION)
    if assignment is None:
        raise ValueError("no provider/model assignment for host_generation")
    try:
        provider = composition.providers.llm_registry.get(assignment.provider)
    except KeyError as exc:
        raise ValueError(f"unknown provider {assignment.provider!r} for host_generation") from exc
    turns = HostTurnService(database, LLMHostTurnProvider(provider, assignment.model))
    decision = DirectorDecision(
        speaker_id=host_ids[0],
        intent=f"Discuss {episode.title}",
        target_duration_seconds=45,
        target_words=80,
    )
    turns.generate(context.run_id, context.episode_id, decision)


# fmt: off
def _tts_stage(
    service: DeeperDiveService,
    project_id: str,
    context: PipelineContext,
) -> None:
    root = service.workspaces.project_root(project_id)
    database = Database(root / "project.db")
    turns = HostTurnService(database).list_turns(context.episode_id)
    if not turns:
        return
    composition = getattr(service, "_production_composition", None)
    if composition is None:
        raise RuntimeError("production composition is unavailable for TTS generation")
    repository = HostEpisodeRepository(database)
    hosts = {
        record.id: HostProfile.from_record(record)
        for record in repository.list_hosts(project_id)
    }
    tts_turns = tuple(
        _tts_turn_for_host(composition, hosts[turn.speaker_id], turn)
        for turn in turns
    )
    TTSGenerationStage(
        composition.providers.tts_registry,
        TTSArtifactRepository(database),
        root / "output" / "tts",
        max_workers=1,
    ).generate(context.run_id, tts_turns)


def _tts_turn_for_host(
    composition: ProductionComposition,
    host: HostProfile,
    turn: HostTurn,
) -> TTSTurn:
    provider, voice = composition.providers.tts_registry.resolve_host(host)
    return TTSTurn(turn.id, turn.speaker_id, turn.text, provider.provider_id, voice.id)


def _composition_stage(
    service: DeeperDiveService,
    project_id: str,
    context: PipelineContext,
) -> None:
    root = service.workspaces.project_root(project_id)
    database = Database(root / "project.db")
    turns = HostTurnService(database).list_turns(context.episode_id)
    if not turns:
        return
    composition = getattr(service, "_production_composition", None)
    if composition is None:
        raise RuntimeError("production composition is unavailable for audio composition")
    artifacts = _tts_artifacts_for_turns(composition, project_id, database, turns)
    items = tuple(
        TimelineItem.clip(
            turn_id=turn.id,
            host_id=turn.speaker_id,
            artifact_id=artifacts[turn.id].artifact_id,
            duration_seconds=max(0.1, len(turn.text.split()) / 150 * 60),
            metadata={"chapter_title": f"Turn {turn.turn_ordinal + 1}"},
        )
        for turn in turns
    )
    AudioTimelineRepository(database).save(AudioTimeline.build(context.episode_id, items))
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    episode_audio = output / f"{context.episode_id}.wav"
    episode_audio.write_bytes(
        b"".join(artifacts[turn.id].path.read_bytes() for turn in turns)
    )


def _tts_artifacts_for_turns(
    composition: ProductionComposition,
    project_id: str,
    database: Database,
    turns: list[HostTurn],
) -> dict[str, TTSArtifact]:
    repository = HostEpisodeRepository(database)
    hosts = {
        record.id: HostProfile.from_record(record)
        for record in repository.list_hosts(project_id)
    }
    artifact_repository = TTSArtifactRepository(database)
    artifacts: dict[str, TTSArtifact] = {}
    missing: list[str] = []
    for turn in turns:
        tts_turn = _tts_turn_for_host(composition, hosts[turn.speaker_id], turn)
        artifact = artifact_repository.get_by_cache_key(TTSGenerationStage.cache_key(tts_turn))
        if artifact is None or not artifact.path.is_file() or artifact.path.stat().st_size == 0:
            missing.append(turn.id)
            continue
        artifacts[turn.id] = artifact
    if missing:
        raise ValueError("missing TTS artifacts for turns: " + ", ".join(missing))
    return artifacts
# fmt: on


def _durable_stage_boundary(context: PipelineContext) -> None:
    """Production-safe no-op for stages that do not yet need richer work.

    The orchestrator still owns durable state transitions, retries, checkpoints,
    pause/cancel boundaries, and progress events. Stage-specific content generation
    can replace these handlers incrementally without changing TUI/CLI wiring.
    """

    _ = context
