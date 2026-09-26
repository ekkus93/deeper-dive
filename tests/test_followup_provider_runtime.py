from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight import PreflightBlockedError
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import UserConfig, UserConfigStore


def test_same_session_provider_save_refreshes_preflight_and_generation(
    tmp_path: Path,
) -> None:
    composition = _empty_composition(tmp_path)
    _save_runtime_providers(composition)
    project_id, episode_id = _ready_episode(composition)
    ffmpeg = _fake_ffmpeg(tmp_path)

    assert composition.provider_controller.llm_registry is composition.providers.llm_registry
    assert composition.preflight_service.llm_registry is composition.providers.llm_registry
    assert composition.preflight_service.tts_registry is composition.providers.tts_registry

    report = GenerationStartService(composition, ffmpeg_executable=ffmpeg).preflight(
        project_id,
        episode_id,
    )
    assert report.ready
    assert {(route.stage, route.provider) for route in report.routes} >= {
        (ModelRole.EPISODE_PLANNING.value, "fresh"),
        (ModelRole.HOST_GENERATION.value, "fresh"),
        ("tts", "speech"),
    }

    run = GenerationStartService(composition, ffmpeg_executable=ffmpeg).start(
        project_id,
        episode_id,
    )
    result = composition.run_generation(project_id, run.run.id)

    assert result.run.state == "completed"
    turns = HostTurnService(composition.database_for_project(project_id)).list_turns(episode_id)
    assert turns
    assert "Configured fake provider host turn marker" in turns[0].text


def test_same_session_provider_remove_blocks_preflight_and_generation(
    tmp_path: Path,
) -> None:
    composition = _empty_composition(tmp_path)
    _save_runtime_providers(composition)
    project_id, episode_id = _ready_episode(composition)
    ffmpeg = _fake_ffmpeg(tmp_path)
    starter = GenerationStartService(composition, ffmpeg_executable=ffmpeg)

    assert starter.preflight(project_id, episode_id).ready

    composition.provider_controller.remove_provider("fresh")

    assert composition.provider_controller.llm_registry is composition.providers.llm_registry
    assert composition.preflight_service.llm_registry is composition.providers.llm_registry
    assert composition.preflight_service.tts_registry is composition.providers.tts_registry
    with pytest.raises(KeyError, match="unknown LLM provider"):
        composition.providers.llm_registry.get("fresh")

    blocked = starter.preflight(project_id, episode_id)
    assert "llm_assignment" in {issue.code for issue in blocked.blockers}
    with pytest.raises(PreflightBlockedError, match="generation blocked by preflight"):
        starter.start(project_id, episode_id)

    stale_run = composition.create_generation_run(project_id, episode_id)
    with pytest.raises(ValueError, match="unknown provider 'fresh'"):
        composition.run_generation(project_id, stale_run.id)

    failed = composition.generation_run_repository(project_id).get(stale_run.id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.stage == "planning"
    assert failed.failure_message is not None
    assert "unknown provider 'fresh'" in failed.failure_message


def test_same_session_tts_remove_updates_preflight_registry(tmp_path: Path) -> None:
    composition = _empty_composition(tmp_path)
    _save_runtime_providers(composition)
    project_id, episode_id = _ready_episode(composition)
    ffmpeg = _fake_ffmpeg(tmp_path)
    starter = GenerationStartService(composition, ffmpeg_executable=ffmpeg)

    assert starter.preflight(project_id, episode_id).ready

    composition.provider_controller.remove_provider("speech")

    assert composition.preflight_service.tts_registry is composition.providers.tts_registry
    with pytest.raises(KeyError, match="unknown TTS provider"):
        composition.providers.tts_registry.get("speech")
    blocked = starter.preflight(project_id, episode_id)
    assert "tts_assignment" in {issue.code for issue in blocked.blockers}


def _empty_composition(tmp_path: Path) -> ProductionComposition:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(UserConfig())
    return ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )


def _save_runtime_providers(composition: ProductionComposition) -> None:
    composition.provider_controller.save_provider(
        "fresh",
        "fake",
        default_model="fake-v1",
    )
    composition.provider_controller.save_provider(
        "speech",
        "fake-tts",
        voices=("voice-a",),
    )
    config = composition.provider_controller.config()
    config.defaults.update(
        {
            ModelRole.EPISODE_PLANNING.value: "fresh:fake-v1",
            ModelRole.HOST_GENERATION.value: "fresh:fake-v1",
        }
    )
    composition.config_store.save(config)
    composition.provider_controller.reload()


def _ready_episode(composition: ProductionComposition) -> tuple[str, str]:
    project = composition.service.create_project("Runtime refresh")
    composition.service.add_pasted_source(
        project.id,
        "Runtime source",
        "Provider runtime refresh should affect generation without a restart.",
    )
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Runtime refresh episode",
            focus="Same-session providers",
            target_duration_seconds=60,
            host_ids=(host.id,),
            research_overrides={"policy": "off"},
        ),
    )
    return project.id, episode.id


def _fake_ffmpeg(tmp_path: Path) -> Path:
    executable = tmp_path / "ffmpeg"
    executable.write_text("fake", encoding="utf-8")
    return executable
