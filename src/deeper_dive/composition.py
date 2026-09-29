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
from deeper_dive.audio_normalization import AudioNormalizationError, CanonicalAudio, normalize_wav
from deeper_dive.audio_playback import AudioPlaybackBackend, AudioPlaybackController
from deeper_dive.audio_timeline import AudioTimeline, AudioTimelineRepository, TimelineItem
from deeper_dive.conversation_generation import ConversationGenerationService
from deeper_dive.conversation_state import ConversationState
from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.director_decision import DirectorDecision
from deeper_dive.domain.clock import SystemClock, format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlanGenerator, EpisodePlannerService, PlannedSegment
from deeper_dive.export import EpisodeExporter
from deeper_dive.generation_monitor import GenerationMonitorController
from deeper_dive.generation_role_providers import (
    LLMDirectorDecisionProvider,
    LLMTranscriptVerifier,
)
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
from deeper_dive.plan_validity import evaluate_episode_plan
from deeper_dive.preflight import PreflightService
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderBuildResult, ProviderFactory
from deeper_dive.provider_runtime import ProviderRuntime
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

_TERMINAL_GENERATION_STATES = frozenset({"completed", "failed", "cancelled"})


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
    provider_runtime: ProviderRuntime
    provider_controller: ProviderController
    research_controller: PersistentResearchController
    preflight_service: PreflightService
    preflight_controller: PreflightController
    generation_monitor_controller: GenerationMonitorController
    benchmark_service: TTSBenchmarkService
    playback_controller: AudioPlaybackController

    @property
    def providers(self) -> ProviderBuildResult:
        """Return the current provider runtime snapshot through one owner."""

        return self.provider_runtime.providers

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
        composition_ref: list[ProductionComposition] = []

        def run_pipeline(run_id: str, progress: ProgressSink) -> None:
            composition_ref[0]._run_generation_pipeline(run_id, progress)

        monitor_controller = GenerationMonitorController(runner=run_pipeline)
        composition = cls(
            service=app_service,
            config_store=config_store,
            provider_runtime=ProviderRuntime(providers),
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
        composition_ref.append(composition)
        composition.attach_provider_controller(provider_controller)
        return composition

    def attach_provider_controller(self, provider_controller: ProviderController) -> None:
        """Attach a provider controller to the production runtime refresh boundary."""

        self.provider_controller = provider_controller
        self.provider_controller.on_reload = self.refresh_providers

    def refresh_providers(self, providers: ProviderBuildResult) -> None:
        """Refresh every production provider consumer after a config rebuild."""

        self.provider_runtime.publish(providers)
        self.provider_controller.llm_registry = providers.llm_registry
        self.provider_controller.tts_providers = providers.tts_providers
        self.preflight_service = PreflightService(
            providers.llm_registry,
            providers.tts_registry,
        )

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
            handlers or _production_stage_handlers(self, project_id),
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

        repository = self.generation_run_repository(project_id)
        try:
            _assignments, errors = self.effective_model_role_assignments_for_run(project_id, run_id)
            if errors:
                raise ValueError("invalid model-role configuration: " + "; ".join(errors))
            return self.generation_pipeline(project_id, progress=progress).run(run_id)
        except Exception as exc:
            self._persist_generation_failure(repository, run_id, exc)
            raise

    @staticmethod
    def _persist_generation_failure(
        repository: GenerationRunRepository,
        run_id: str,
        exc: BaseException,
    ) -> None:
        run = repository.get(run_id)
        if run is None or run.state in _TERMINAL_GENERATION_STATES:
            return
        failed = GenerationRunRepository.with_failure(
            run,
            code="generation_execution_failed",
            sanitized_message=sanitize_exception_message(exc),
            modified_at=format_timestamp(SystemClock().now()),
        )
        repository.update(failed)

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

    def plan_episode(self, project_id: str, context: PipelineContext) -> None:
        """Run the public production planning operation for one pipeline context."""

        _planning_stage(self, project_id, context)

    def generate_episode_conversation(
        self, project_id: str, context: PipelineContext
    ) -> None:
        """Run the public production conversation operation for one pipeline context."""

        _conversation_stage(self, project_id, context)

    def verify_episode_transcript(self, project_id: str, context: PipelineContext) -> None:
        """Run the public production verification operation for one pipeline context."""

        _verification_stage(self, project_id, context)

    def generate_episode_tts(self, project_id: str, context: PipelineContext) -> None:
        """Run the public production TTS operation for one pipeline context."""

        _tts_stage(self, project_id, context)

    def compose_episode_audio(self, project_id: str, context: PipelineContext) -> None:
        """Run the public production audio-composition operation for one pipeline context."""

        _composition_stage(self, project_id, context)

    def regenerate_episode_audio(
        self,
        project_id: str,
        episode_id: str,
        *,
        run_id: str = "transcript-repair",
    ) -> None:
        """Regenerate TTS artifacts, timeline, and episode audio via production wiring."""

        try:
            self.generate_episode_tts(
                project_id,
                PipelineContext(run_id, episode_id, "tts"),
            )
            self.compose_episode_audio(
                project_id,
                PipelineContext(run_id, episode_id, "composition"),
            )
        except Exception as exc:
            safe_message = sanitize_exception_message(exc)
            raise RuntimeError(f"episode audio regeneration failed: {safe_message}") from exc

    def _run_generation_pipeline(
        self,
        run_id: str,
        progress: ProgressSink,
    ) -> None:
        project_id = _project_id_for_run(self.service, run_id)
        self.generation_pipeline(project_id, progress=progress).run(run_id)


def _project_id_for_run(service: DeeperDiveService, run_id: str) -> str:
    for project in service.list_projects():
        if service.runs(project.id).get(run_id) is not None:
            return project.id
    raise KeyError(f"unknown generation run: {run_id}")


def _production_stage_handlers(
    composition: ProductionComposition,
    project_id: str,
) -> dict[str, StageHandler]:
    handlers = {stage: _durable_stage_boundary for stage in DEFAULT_STAGES}
    handlers["planning"] = lambda context: composition.plan_episode(project_id, context)
    handlers["conversation"] = lambda context: composition.generate_episode_conversation(
        project_id, context
    )
    handlers["verification"] = lambda context: composition.verify_episode_transcript(
        project_id, context
    )
    handlers["tts"] = lambda context: composition.generate_episode_tts(project_id, context)
    handlers["composition"] = lambda context: composition.compose_episode_audio(
        project_id, context
    )
    return handlers


def _planning_stage(
    composition: ProductionComposition,
    project_id: str,
    context: PipelineContext,
) -> None:
    database = composition.database_for_project(project_id)
    if evaluate_episode_plan(database, context.episode_id).usable:
        return
    assignments, errors = composition.effective_model_role_assignments_for_episode(
        project_id,
        context.episode_id,
    )
    if errors:
        raise ValueError("invalid model-role configuration: " + "; ".join(errors))
    provider, model = _llm_provider_for_role(
        composition,
        assignments,
        model_roles.ModelRole.EPISODE_PLANNING,
    )
    planner = composition.planning_service(project_id, LLMEpisodePlanGenerator(provider, model))
    planner.build_plan(context.episode_id)


def _conversation_stage(
    composition: ProductionComposition,
    project_id: str,
    context: PipelineContext,
) -> None:
    database = composition.database_for_project(project_id)
    repository = HostEpisodeRepository(database)
    host_ids = tuple(repository.list_episode_host_ids(context.episode_id))
    if not host_ids:
        return
    episode = repository.get_episode(context.episode_id)
    if episode is None:
        raise KeyError(context.episode_id)
    assignments, errors = composition.effective_model_role_assignments_for_episode(
        project_id, context.episode_id
    )
    if errors:
        raise ValueError("invalid model-role configuration: " + "; ".join(errors))
    provider, model = _llm_provider_for_role(
        composition,
        assignments,
        model_roles.ModelRole.HOST_GENERATION,
    )

    decision_provider = None
    if assignments.resolve(model_roles.ModelRole.DIRECTING) is not None:
        director_provider, director_model = _llm_provider_for_role(
            composition,
            assignments,
            model_roles.ModelRole.DIRECTING,
        )
        director = LLMDirectorDecisionProvider(director_provider, director_model)

        def decide(
            segment: PlannedSegment,
            hosts: tuple[HostProfile, ...],
            state: ConversationState,
            remaining_seconds: int,
        ) -> DirectorDecision:
            return director.decide(
                episode_title=episode.title,
                host_ids=tuple(host.id for host in hosts),
                available_evidence_ids=segment.evidence_ids,
                segment=segment,
                state=state,
                remaining_seconds=remaining_seconds,
            )

        decision_provider = decide

    ConversationGenerationService(
        database,
        LLMHostTurnProvider(provider, model),
        decision_provider=decision_provider,
        available_evidence_ids=_project_indexed_evidence_ids(database, project_id),
    ).run(context.run_id, context.episode_id)


def _episode_evidence_ids(database: Database, episode_id: str) -> tuple[str, ...]:
    repository = HostEpisodeRepository(database)
    episode = repository.get_episode(episode_id)
    if episode is None:
        return ()
    plan = repository.get_plan(episode_id)
    if plan is None:
        return ()
    valid_evidence_ids = _project_indexed_evidence_ids(database, episode.project_id)
    evidence: list[str] = []
    for segment in repository.list_segments(plan.id):
        payload = json.loads(segment.segment_json)
        for evidence_id in payload.get("evidence_ids", ()):
            normalized = str(evidence_id)
            if normalized and normalized in valid_evidence_ids and normalized not in evidence:
                evidence.append(normalized)
    return tuple(evidence)


def _project_indexed_evidence_ids(database: Database, project_id: str) -> set[str]:
    with database.connection() as db:
        rows = db.execute(
            """SELECT c.id FROM source_chunks c JOIN sources s ON s.id=c.source_id
            WHERE s.project_id=? AND s.included=1 AND s.status='indexed'
            ORDER BY s.imported_at,s.id,c.ordinal,c.id""",
            (project_id,),
        ).fetchall()
    return {str(row["id"]) for row in rows}


def _verification_stage(
    composition: ProductionComposition,
    project_id: str,
    context: PipelineContext,
) -> None:
    database = composition.database_for_project(project_id)
    turns = tuple(HostTurnService(database).list_turns(context.episode_id))
    if not turns:
        return
    assignments, errors = composition.effective_model_role_assignments_for_episode(
        project_id, context.episode_id
    )
    if errors:
        raise ValueError("invalid model-role configuration: " + "; ".join(errors))
    if assignments.resolve(model_roles.ModelRole.VERIFICATION) is None:
        return
    provider, model = _llm_provider_for_role(
        composition,
        assignments,
        model_roles.ModelRole.VERIFICATION,
    )
    LLMTranscriptVerifier(provider, model).verify(
        episode_id=context.episode_id,
        turns=turns,
    )


def _llm_provider_for_role(
    composition: ProductionComposition,
    assignments: model_roles.ModelRoleAssignments,
    role: model_roles.ModelRole,
) -> tuple[LLMProvider, str]:
    assignment = assignments.resolve(role)
    if assignment is None:
        raise ValueError(f"no provider/model assignment for {role.value}")
    try:
        provider = composition.providers.llm_registry.get(assignment.provider)
    except KeyError as exc:
        raise ValueError(f"unknown provider {assignment.provider!r} for {role.value}") from exc
    return provider, assignment.model


# fmt: off
def _tts_stage(
    composition: ProductionComposition,
    project_id: str,
    context: PipelineContext,
) -> None:
    root = composition.service.workspaces.project_root(project_id)
    database = Database(root / "project.db")
    turns = HostTurnService(database).list_turns(context.episode_id)
    if not turns:
        return
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
    provider_config = composition.provider_controller.config().providers.get(provider.provider_id)
    model = None if provider_config is None else provider_config.default_model
    settings: dict[str, Any] | None = None
    if provider_config is not None:
        response_format = provider_config.response_format.strip().lower() or "wav"
        if response_format != "wav":
            settings = {"response_format": response_format}
    return TTSTurn(
        turn.id,
        turn.speaker_id,
        turn.text,
        provider.provider_id,
        voice.id,
        model=model,
        settings=settings,
    )


def _composition_stage(
    composition: ProductionComposition,
    project_id: str,
    context: PipelineContext,
) -> None:
    root = composition.service.workspaces.project_root(project_id)
    database = Database(root / "project.db")
    turns = HostTurnService(database).list_turns(context.episode_id)
    if not turns:
        return
    artifacts = _tts_artifacts_for_turns(composition, project_id, database, turns)
    audio_by_turn = {
        turn.id: _normalized_wav_artifact(turn.id, artifacts[turn.id]) for turn in turns
    }
    items = tuple(
        TimelineItem.clip(
            turn_id=turn.id,
            host_id=turn.speaker_id,
            artifact_id=artifacts[turn.id].artifact_id,
            duration_seconds=audio_by_turn[turn.id].duration_seconds,
            metadata={"chapter_title": f"Turn {turn.turn_ordinal + 1}"},
        )
        for turn in turns
    )
    AudioTimelineRepository(database).save(AudioTimeline.build(context.episode_id, items))
    output = root / "output"
    episode_audio = output / f"{context.episode_id}.wav"
    EpisodeExporter.write_wav(
        episode_audio,
        _combine_wav_audio(tuple(audio_by_turn[turn.id] for turn in turns)),
    )


def _normalized_wav_artifact(turn_id: str, artifact: TTSArtifact) -> CanonicalAudio:
    suffix = artifact.path.suffix.lower().lstrip(".")
    if suffix != "wav":
        raise ValueError(
            f"unsupported TTS artifact format for turn {turn_id}: "
            f"{suffix or 'unknown'}; WAV composition is supported"
        )
    try:
        audio = artifact.path.read_bytes()
    except OSError as exc:
        raise ValueError(f"unreadable TTS artifact for turn {turn_id}: {exc}") from exc
    try:
        return normalize_wav(audio)
    except AudioNormalizationError as exc:
        raise ValueError(f"invalid WAV TTS artifact for turn {turn_id}: {exc}") from exc


def _combine_wav_audio(chunks: tuple[CanonicalAudio, ...]) -> CanonicalAudio:
    if not chunks:
        raise ValueError("cannot compose an episode with no TTS audio")
    first = chunks[0]
    pcm = b"".join(chunk.pcm for chunk in chunks)
    frame_size = first.channels * first.sample_width_bytes
    duration = len(pcm) / frame_size / first.sample_rate_hz
    return CanonicalAudio(
        pcm=pcm,
        sample_rate_hz=first.sample_rate_hz,
        channels=first.channels,
        sample_width_bytes=first.sample_width_bytes,
        duration_seconds=duration,
        source_format="wav",
        source_media_type="audio/wav",
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
