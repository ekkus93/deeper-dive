from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_readiness import (
    ProductionWizardCompletion,
    first_run_readiness,
)
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.model_roles import ModelRole
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.research_policy import ResearchMode, ResearchPolicy
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _configured_composition(
    tmp_path: Path,
    *,
    speech_deferred: bool = False,
) -> ProductionComposition:
    data_dir = tmp_path / "data"
    defaults = {role.value: "planner:fake-v1" for role in ModelRole}
    defaults.update(
        {
            "quick_deep_dive_duration_minutes": "20",
            "research_policy": "useful",
        }
    )
    providers = {
        "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
    }
    if speech_deferred:
        defaults["speech_setup"] = "deferred"
    else:
        providers["speech"] = ProviderConfig(provider_type="fake-tts")
        defaults["tts_provider"] = "speech"
        defaults["tts_voice"] = "voice-a"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(providers=providers, defaults=defaults)
    )
    return ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )


def test_first_run_completion_is_recomputed_from_durable_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition = _configured_composition(tmp_path)
    monkeypatch.setattr(
        "deeper_dive.first_run.shutil.which",
        lambda _name: "/usr/bin/ffmpeg",
    )
    context = WizardContext(
        composition,
        WizardState(WizardKind.FIRST_RUN, "ready"),
    )

    readiness = first_run_readiness(context)

    assert readiness.llm_provider_ready
    assert readiness.model_roles_ready
    assert readiness.speech_choice_made
    assert readiness.audio_ready
    assert readiness.setup_ready
    assert ProductionWizardCompletion(context)("ready")

    config = composition.provider_controller.config()
    config.defaults.pop("verification")
    composition.provider_controller.config_store.save(config)

    assert not first_run_readiness(context).model_roles_ready
    assert not ProductionWizardCompletion(context)("ready")


def test_first_run_explicit_no_speech_can_complete_without_audio_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition = _configured_composition(tmp_path, speech_deferred=True)
    monkeypatch.setattr("deeper_dive.first_run.shutil.which", lambda _name: None)
    context = WizardContext(
        composition,
        WizardState(WizardKind.FIRST_RUN, "ready"),
    )

    readiness = first_run_readiness(context)

    assert readiness.speech_deferred
    assert readiness.speech_choice_made
    assert not readiness.audio_ready
    assert readiness.setup_ready


def test_new_deep_dive_completion_advances_only_with_durable_production_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition = _configured_composition(tmp_path)
    context = WizardContext(
        composition,
        WizardState(WizardKind.NEW_DEEP_DIVE, "project"),
    )
    completion = ProductionWizardCompletion(context)

    assert not completion("project")
    project = composition.service.create_project("Guided readiness")
    context.project_id = project.id
    assert completion("project")
    assert not completion("sources")
    assert not completion("research")
    assert not completion("hosts")
    assert not completion("episode")
    assert not completion("plan")
    assert not completion("preflight")

    composition.service.add_pasted_source(
        project.id,
        "Guided source",
        "Deterministic source material for guided readiness.",
    )
    assert completion("sources")

    composition.research_controller.save_policy(
        project.id,
        ResearchPolicy(mode=ResearchMode.OFF),
        "",
    )
    assert completion("research")

    host = create_host_from_preset("curious_explainer", project.id)
    host_record = replace(
        host.to_record(),
        tts_provider="speech",
        tts_voice="voice-a",
    )
    composition.service.hosts(project.id).create_host(host_record)
    episode = EpisodeConfigurationService(
        composition.database_for_project(project.id)
    ).create(
        project.id,
        EpisodeConfiguration(
            title="Guided readiness episode",
            focus="Prove durable guided completion",
            target_duration_seconds=60,
            host_ids=(host.id,),
        ),
    )
    context.episode_id = episode.id
    assert completion("hosts")
    assert completion("episode")
    assert not completion("plan")

    composition.configured_planning_service(
        project.id,
        "planner",
        "fake-v1",
    ).build_plan(episode.id)
    assert completion("plan")

    monkeypatch.setattr(
        "deeper_dive.preflight.FFmpegConfig.detect",
        staticmethod(lambda executable=None: executable or Path("/fake/ffmpeg")),
    )
    assert completion("preflight")


def test_research_step_requires_an_explicit_durable_project_policy(
    tmp_path: Path,
) -> None:
    composition = _configured_composition(tmp_path)
    project = composition.service.create_project("Research choice")
    context = WizardContext(
        composition,
        WizardState(WizardKind.NEW_DEEP_DIVE, "research"),
        project_id=project.id,
    )
    completion = ProductionWizardCompletion(context)

    assert not completion("research")
    composition.research_controller.save_policy(
        project.id,
        ResearchPolicy(mode=ResearchMode.USEFUL),
        "",
    )
    assert completion("research")
