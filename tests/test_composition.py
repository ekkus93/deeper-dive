from __future__ import annotations

import json

from deeper_dive.composition import LLMEpisodePlanGenerator, ProductionComposition
from deeper_dive.llm import FakeLLMProvider
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
    )

    assert composition.provider_controller.llm_registry.provider_ids() == ("planner",)
    assert tuple(composition.provider_controller.tts_providers) == ("speech",)
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
