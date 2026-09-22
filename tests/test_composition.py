from __future__ import annotations

import json

from deeper_dive.application.events import ProgressEvent
from deeper_dive.composition import LLMEpisodePlanGenerator, ProductionComposition
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.llm import FakeLLMProvider
from deeper_dive.model_roles import ModelAssignment, ModelRole
from deeper_dive.pipeline import DEFAULT_STAGES, PipelineContext
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
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
    )

    assert composition.provider_controller.llm_registry.provider_ids() == ("planner",)
    assert tuple(composition.provider_controller.tts_providers) == ("speech",)
    assert composition.preflight_service.llm_registry is composition.providers.llm_registry
    assert composition.preflight_service.tts_registry is composition.providers.tts_registry
    assert composition.benchmark_service is not None
    assert composition.playback_controller is not None
    assert (
        composition.research_controller.database_for_project(
            "12345678-1234-5678-1234-567812345678"
        ).name
        == "project.db"
    )


def test_production_composition_constructs_planner_with_injectable_provider_boundary(
    tmp_path,
) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Composition planner")

    planner = composition.planning_service(project.id, _PlanGenerator())

    assert planner.database.path == composition.database_for_project(project.id).path
    assert isinstance(planner.generator, _PlanGenerator)


def test_llm_episode_plan_generator_uses_normalized_provider_boundary() -> None:
    response = json.dumps({"segments": [{"title": "Opening"}]})
    provider = FakeLLMProvider(response=response)
    generator = LLMEpisodePlanGenerator(provider, "fake-v1")

    payload = generator.generate_plan({"episode": {"title": "Test"}})

    assert payload == {"segments": [{"title": "Opening"}]}
    assert provider.requests[0].model == "fake-v1"
    expected_schema = {"type": "object", "required": ["segments"]}
    assert provider.requests[0].response_schema == expected_schema


def test_configured_planning_service_resolves_persisted_provider(tmp_path) -> None:
    data_dir = tmp_path / "data"
    config_store = UserConfigStore(data_dir / "config.json")
    provider_config = ProviderConfig(provider_type="fake", default_model="fake-v1")
    config_store.save(UserConfig(providers={"planner": provider_config}))
    factory = ProviderFactory(environ={})
    composition = ProductionComposition.build(data_dir, provider_factory=factory)
    project = composition.service.create_project("Configured planner")

    planner = composition.configured_planning_service(project.id, "planner", "fake-v1")

    assert isinstance(planner.generator, LLMEpisodePlanGenerator)
    assert planner.generator.provider.provider_id == "planner"
    assert planner.generator.model == "fake-v1"


def test_production_composition_resolves_durable_episode_overrides_before_project_and_user(
    tmp_path,
) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            defaults={
                "episode_planning": "user-provider:user-model",
                "host_generation": "user-provider:user-host-model",
            }
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project(
        "Precedence project",
        instructions=json.dumps(
            {
                "model_defaults": {
                    "episode_planning": "project-provider:project-model",
                    "directing": "project-provider:project-directing-model",
                }
            }
        ),
    )
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Precedence episode",
            model_overrides={
                "episode_planning": {
                    "provider": "episode-provider",
                    "model": "episode-model",
                }
            },
        ),
    )

    assignments, errors = composition.effective_model_role_assignments_for_episode(
        project.id, episode.id
    )

    assert not errors
    assert assignments.resolve(ModelRole.EPISODE_PLANNING) == ModelAssignment(
        "episode-provider", "episode-model"
    )
    assert assignments.resolve(ModelRole.DIRECTING) == ModelAssignment(
        "project-provider", "project-directing-model"
    )
    assert assignments.resolve(ModelRole.HOST_GENERATION) == ModelAssignment(
        "user-provider", "user-host-model"
    )


def test_production_composition_can_plan_and_generate_with_deterministic_provider(tmp_path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={"planner": ProviderConfig(provider_type="fake", default_model="fake-v1")}
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Composed deterministic application")
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Composed episode",
            focus="Exercise production composition",
            target_duration_seconds=1200,
        ),
    )

    plan = composition.configured_planning_service(project.id, "planner", "fake-v1").build_plan(
        episode.id
    )
    run = composition.create_generation_run(project.id, episode.id)
    result = composition.run_generation(project.id, run.id)

    assert plan.episode_id == episode.id
    assert plan.segments
    assert result.run.state == "completed"
    assert composition.generation_run_repository(project.id).list_completed_stages(run.id) == list(
        DEFAULT_STAGES
    )


def test_production_composition_constructs_generation_run_and_pipeline(tmp_path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Composition pipeline")
    timestamp = "2026-09-20T00:00:00.000000Z"
    episode_id = str(new_episode_id())
    composition.service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            created_at=timestamp,
            modified_at=timestamp,
        ),
        [],
    )
    visited: list[str] = []

    def handler(context: PipelineContext) -> None:
        visited.append(f"{context.run_id}:{context.stage}")

    run = composition.create_generation_run(project.id, episode_id)
    events: list[ProgressEvent] = []
    pipeline = composition.generation_pipeline(
        project.id,
        progress=events.append,
        handlers={stage: handler for stage in DEFAULT_STAGES},
    )

    result = pipeline.run(run.id)

    assert run.state == "pending"
    assert result.run.state == "completed"
    assert [item.split(":", 1)[1] for item in visited] == list(DEFAULT_STAGES)
    assert composition.generation_run_repository(project.id).list_completed_stages(run.id) == list(
        DEFAULT_STAGES
    )
    assert events[-1].operation == "pipeline"
    assert events[-1].state == "completed"


def test_production_composition_monitor_runner_executes_durable_pipeline(tmp_path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Monitor runner")
    timestamp = "2026-09-20T00:00:00.000000Z"
    episode_id = str(new_episode_id())
    composition.service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            created_at=timestamp,
            modified_at=timestamp,
        ),
        [],
    )
    run_id = str(new_run_id())
    repository = composition.service.runs(project.id)
    repository.create(
        GenerationRunRecord(run_id, episode_id, "sources", "pending", timestamp, timestamp)
    )
    runner = composition.generation_monitor_controller.runner
    events: list[ProgressEvent] = []

    assert runner is not None
    runner(run_id, events.append)

    run = repository.get(run_id)
    assert run is not None
    assert run.state == "completed"
    assert repository.list_completed_stages(run_id) == list(DEFAULT_STAGES)
    assert events[-1].operation == "pipeline"
    assert events[-1].state == "completed"
