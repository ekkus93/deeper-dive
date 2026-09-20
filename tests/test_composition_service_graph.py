from __future__ import annotations

from deeper_dive.audio_playback import AudioPlaybackController
from deeper_dive.composition import ProductionComposition
from deeper_dive.export import EpisodeExporter
from deeper_dive.generation_monitor import GenerationMonitorController
from deeper_dive.pipeline import DEFAULT_STAGES, PipelineContext, PipelineOrchestrator
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.targeted_repair import TargetedRepairService
from deeper_dive.tts_benchmark import TTSBenchmarkService


class _PlanGenerator:
    def generate_plan(self, request):
        return {
            "segments": [
                {
                    "title": "Opening",
                    "purpose": "Introduce",
                    "target_duration_seconds": 60,
                }
            ]
        }


class _RepairProvider:
    def regenerate_turn(self, *args, **kwargs):
        raise AssertionError("not called")


class _Rechecker:
    def recheck(self, *args, **kwargs):
        raise AssertionError("not called")


class _SummaryUpdater:
    def update(self, *args, **kwargs):
        raise AssertionError("not called")


def test_production_composition_constructs_shared_service_graph(tmp_path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data", provider_factory=ProviderFactory(environ={})
    )
    project = composition.service.create_project("Composition graph")

    planner = composition.planning_service(project.id, _PlanGenerator())
    pipeline = composition.pipeline_service(
        project.id,
        {stage: (lambda context: None) for stage in DEFAULT_STAGES},
    )
    exporter = composition.exporter(project.id)
    repair = composition.targeted_repair_service(
        project.id, _RepairProvider(), _Rechecker(), _SummaryUpdater()
    )

    database_path = composition.database_for_project(project.id).path
    assert planner.database.path == database_path
    assert isinstance(pipeline, PipelineOrchestrator)
    assert pipeline.repository.database.path == database_path
    assert isinstance(exporter, EpisodeExporter)
    assert isinstance(repair, TargetedRepairService)
    assert repair.database.path == database_path
    assert isinstance(composition.preflight_controller, PreflightController)
    assert isinstance(composition.generation_monitor_controller, GenerationMonitorController)
    assert isinstance(composition.benchmark_service, TTSBenchmarkService)
    assert isinstance(composition.playback_controller, AudioPlaybackController)


def test_pipeline_stage_handlers_remain_injectable_through_composition(tmp_path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data", provider_factory=ProviderFactory(environ={})
    )
    project = composition.service.create_project("Injectable graph")
    seen: list[str] = []

    def handler(context: PipelineContext) -> None:
        seen.append(context.stage)

    handlers = {stage: handler for stage in DEFAULT_STAGES}
    orchestrator = composition.pipeline_service(project.id, handlers)

    assert all(orchestrator.handlers[stage] is handler for stage in DEFAULT_STAGES)
    assert seen == []
