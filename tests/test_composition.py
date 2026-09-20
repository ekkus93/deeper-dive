from __future__ import annotations

from deeper_dive.audio_playback import NoAudioPlayerBackend
from deeper_dive.composition import ProductionComposition
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class _PlanGenerator:
    def generate_plan(self, request):
        return {"segments": []}


def test_production_composition_loads_persisted_providers(tmp_path) -> None:
    data_dir = tmp_path / "data"
    config_store = UserConfigStore(data_dir / "config.json")
    config_store.save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            }
        )
    )

    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
        playback_backend=NoAudioPlayerBackend(),
    )

    assert composition.provider_controller.llm_registry.provider_ids() == ("planner",)
    assert tuple(composition.provider_controller.tts_providers) == ("speech",)
    assert (
        composition.research_controller.database_for_project(
            "12345678-1234-5678-1234-567812345678"
        ).name
        == "project.db"
    )
    assert composition.playback_controller.capabilities.strategy == "none"


def test_production_composition_constructs_planner_with_injectable_provider_boundary(
    tmp_path,
) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
        playback_backend=NoAudioPlayerBackend(),
    )
    project = composition.service.create_project("Composition planner")

    planner = composition.planning_service(project.id, _PlanGenerator())

    assert planner.database.path == composition.database_for_project(project.id).path
    assert isinstance(planner.generator, _PlanGenerator)


def test_production_composition_constructs_generation_support_services(tmp_path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
        playback_backend=NoAudioPlayerBackend(),
    )
    project = composition.service.create_project("Composition services")
    handlers = {stage: (lambda context: None) for stage in DEFAULT_STAGES}

    pipeline = composition.pipeline_service(project.id, handlers)
    exporter = composition.exporter(project.id)

    assert (
        pipeline.repository.database.path
        == composition.database_for_project(project.id).path
    )
    assert (
        exporter.output_dir
        == composition.service.workspaces.project_root(project.id) / "exports"
    )
    assert composition.benchmark_service is not None
