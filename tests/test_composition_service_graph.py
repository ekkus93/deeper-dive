from __future__ import annotations

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.export import EpisodeExporter
from deeper_dive.pipeline import DEFAULT_STAGES, PipelineOrchestrator
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.targeted_repair import TargetedRepairService


class _Planner:
    def generate_plan(self, request):
        return {"segments": []}


class _RepairProvider:
    def repair_turn(self, turn, feedback, evidence_ids):
        return turn.text


class _Rechecker:
    def recheck_turn(self, turn):
        return None


class _SummaryUpdater:
    def update_after_repair(self, episode_id, turn_id):
        return None


def test_production_composition_constructs_shared_service_graph(tmp_path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Service graph")

    planner = composition.planning_service(project.id, _Planner())
    pipeline = composition.pipeline_service(
        project.id,
        {stage: lambda context: None for stage in DEFAULT_STAGES},
    )
    exporter = composition.exporter(project.id)
    repair = composition.targeted_repair_service(
        project.id,
        _RepairProvider(),
        _Rechecker(),
        _SummaryUpdater(),
    )

    assert isinstance(planner, EpisodePlannerService)
    assert isinstance(pipeline, PipelineOrchestrator)
    assert isinstance(exporter, EpisodeExporter)
    assert isinstance(repair, TargetedRepairService)
    assert composition.preflight_controller is not None
    assert composition.benchmark_service is not None
    assert composition.playback_controller is not None
    assert planner.database.path == composition.database_for_project(project.id).path
    assert repair.database.path == composition.database_for_project(project.id).path
