from __future__ import annotations

from pathlib import Path

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_production_composition_plan_preflight_generate_review_export(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={"planner": ProviderConfig(provider_type="fake", default_model="fake-v1")},
            defaults={"episode_planning": "planner:fake-v1"},
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    assert composition.provider_controller.llm_registry.provider_ids() == ("planner",)

    project = composition.service.create_project("DDR-103 acceptance")
    source = composition.service.add_pasted_source(
        project.id,
        "Synthetic source",
        "A deterministic local source used for production-composition acceptance.",
    )
    assert composition.service.list_source_chunks(project.id, source.id)

    host = create_host_from_preset("curious_explainer", project.id)
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Acceptance episode",
            focus="Exercise the shared production workflow",
            target_duration_seconds=60,
            host_ids=(host.id,),
        ),
    )
    plan = composition.configured_planning_service(project.id, "planner", "fake-v1").build_plan(
        episode.id
    )
    assert plan.segments

    app = DeeperDiveApp(composition.service)
    app.current_project_id = project.id
    app.current_project_name = project.name
    app.current_episode_id = episode.id
    preflight = composition.preflight_controller.build(app)
    assert preflight.source_count == 1
    assert preflight.indexed_source_count == 1
    assert preflight.host_count == 1
    assert preflight.report.ready, preflight.report.blockers

    run = composition.create_generation_run(project.id, episode.id)
    completed = composition.run_generation(project.id, run.id).run
    assert completed.state == "completed"

    review = TranscriptReviewController()
    turns = review.turns(app)
    assert turns
    assert all(turn.text for turn in turns)
    review_path = review.export_markdown(app)
    assert review_path.is_file()
    assert "deterministic production turn" in review_path.read_text(encoding="utf-8")

    exported = EpisodeLibraryExportService(composition.service.workspaces).export(
        project.id,
        episode,
        completed,
    )
    assert exported.transcript.is_file()
    assert exported.manifest.is_file()
    assert exported.metadata.is_file()
    assert exported.audio is not None
    assert exported.audio.is_file()
    assert exported.audio.read_bytes().startswith(b"FAKE-WAV")
