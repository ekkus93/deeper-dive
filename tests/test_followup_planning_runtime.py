from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.llm import FakeLLMProvider, LLMProvider
from deeper_dive.model_roles import ModelRole
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class _PlanningResponseFactory(ProviderFactory):
    def _llm(self, kind: str, config: ProviderConfig) -> LLMProvider:
        if kind == "fake" and config.default_model == "bad-v1":
            return FakeLLMProvider(model="bad-v1", response=json.dumps({"segments": []}))
        return super()._llm(kind, config)


def test_pipeline_auto_planning_uses_configured_episode_planning_role(
    tmp_path: Path,
) -> None:
    composition = _composition_with_two_planners(tmp_path)
    project_id, episode_id = _ready_episode(composition)

    run = composition.create_generation_run(project_id, episode_id)
    completed = composition.run_generation(project_id, run.id).run

    plan = composition.service.hosts(project_id).get_plan(episode_id)
    assert completed.state == "completed"
    assert plan is not None
    segments = composition.service.hosts(project_id).list_segments(plan.id)
    assert segments


def test_pipeline_auto_planning_fails_durably_on_invalid_configured_output(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data-invalid"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="bad-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={role.value: "planner:bad-v1" for role in ModelRole},
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=_PlanningResponseFactory(environ={}),
    )
    project_id, episode_id = _ready_episode(composition)
    run = composition.create_generation_run(project_id, episode_id)

    with pytest.raises(ValueError, match="episode plan must contain a non-empty segments list"):
        composition.run_generation(project_id, run.id)

    failed = composition.generation_run_repository(project_id).get(run.id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.stage == "planning"
    assert failed.failure_message is not None
    assert "non-empty segments" in failed.failure_message
    assert composition.service.hosts(project_id).get_plan(episode_id) is None


def _composition_with_two_planners(tmp_path: Path) -> ProductionComposition:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "aaa-sorted-first": ProviderConfig(
                    provider_type="fake",
                    default_model="bad-v1",
                ),
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={role.value: "planner:fake-v1" for role in ModelRole},
        )
    )
    return ProductionComposition.build(
        data_dir,
        provider_factory=_PlanningResponseFactory(environ={}),
    )


def _ready_episode(composition: ProductionComposition) -> tuple[str, str]:
    project = composition.service.create_project("Follow-up planning")
    composition.service.add_pasted_source(
        project.id,
        "Source",
        "Planning should use the configured episode_planning provider.",
    )
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Configured planning episode",
            focus="Configured planning",
            target_duration_seconds=60,
            host_ids=(host.id,),
            research_overrides={"policy": "off"},
        ),
    )
    return project.id, episode.id
