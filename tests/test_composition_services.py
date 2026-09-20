from deeper_dive.audio_playback import NoAudioPlayerBackend
from deeper_dive.composition import ProductionComposition
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.provider_factory import ProviderFactory


def test_composition_constructs_generation_support_services(tmp_path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
        playback_backend=NoAudioPlayerBackend(),
    )
    project = composition.service.create_project("Composition services")
    handlers = {stage: (lambda context: None) for stage in DEFAULT_STAGES}

    pipeline = composition.pipeline_service(project.id, handlers)
    exporter = composition.exporter(project.id)
    database = composition.database_for_project(project.id)
    project_root = composition.service.workspaces.project_root(project.id)

    assert pipeline.repository.database.path == database.path
    assert exporter.output_dir == project_root / "exports"
    assert composition.benchmark_service is not None
    assert composition.playback_controller.capabilities.strategy == "none"
