from __future__ import annotations

from deeper_dive.audio_playback import AudioPlaybackController
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.export import EpisodeExporter
from deeper_dive.pipeline import DEFAULT_STAGES, PipelineOrchestrator
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.tts_benchmark import TTSBenchmarkService


class _PlanGenerator:
    def generate_plan(self, request):
        return {"segments": [{"title": "test", "target_duration_seconds": 1}]}


def _stage_handler(context) -> None:
    _ = context


def test_production_composition_owns_shared_service_construction(tmp_path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Service graph")
    handlers = {stage: _stage_handler for stage in DEFAULT_STAGES}

    planner = composition.planning_service(project.id, _PlanGenerator())
    pipeline = composition.pipeline_service(project.id, handlers)
    exporter = composition.exporter(project.id)

    assert isinstance(planner, EpisodePlannerService)
    assert isinstance(pipeline, PipelineOrchestrator)
    assert isinstance(exporter, EpisodeExporter)
    assert isinstance(composition.preflight_controller, PreflightController)
    assert isinstance(composition.benchmark_service, TTSBenchmarkService)
    assert isinstance(composition.playback_controller, AudioPlaybackController)
    assert planner.database.path == composition.database_for_project(project.id).path
    assert pipeline.repository.database.path == composition.database_for_project(project.id).path
    assert getattr(composition.service, "_production_composition") is composition
