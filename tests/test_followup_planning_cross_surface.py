from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from deeper_dive import cli
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.generation_monitor import GenerationMonitorController
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight import PreflightBlockedError
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore

UNAVAILABLE_MODEL = "model 'missing-v1' is unavailable from provider 'planner'"
EMPTY_SEGMENTS = "episode plan must contain a non-empty segments list"


@dataclass(slots=True)
class TuiAppStub:
    composition: ProductionComposition
    preflight_controller: PreflightController
    generation_monitor_controller: GenerationMonitorController | None = None
    current_project_id: str | None = None
    current_project_name: str | None = None
    current_episode_id: str | None = None
    current_run_id: str | None = None
    last_navigation: str | None = None

    @property
    def service(self):
        return self.composition.service

    @property
    def provider_controller(self):
        return self.composition.provider_controller

    def action_navigate(self, destination: str) -> None:
        self.last_navigation = destination


def test_cli_episode_generate_exposes_planning_preflight_failure(
    tmp_path: Path,
    capsys,
) -> None:
    composition = composition_with_missing_planning_model(tmp_path)
    project_id, episode_id = ready_episode(composition)

    code = cli.main(
        [
            "--data-dir",
            str(composition.service.workspaces.data_dir),
            "episode",
            "generate",
            project_id,
            episode_id,
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "generation blocked by preflight" in captured.err
    assert UNAVAILABLE_MODEL in captured.err
    assert composition.service.hosts(project_id).get_plan(episode_id) is None


def test_tui_generate_controller_exposes_planning_preflight_failure(tmp_path: Path) -> None:
    composition = composition_with_missing_planning_model(tmp_path)
    project_id, episode_id = ready_episode(composition)
    controller = PreflightController(ffmpeg_executable=fake_ffmpeg(tmp_path))
    app = TuiAppStub(
        composition=composition,
        preflight_controller=controller,
        current_project_id=project_id,
        current_project_name="Follow-up planning",
        current_episode_id=episode_id,
    )

    presentation = controller.build(app)

    assert not presentation.report.ready
    assert any(
        UNAVAILABLE_MODEL in blocker.message for blocker in presentation.report.blockers
    )
    with pytest.raises(PreflightBlockedError, match="generation blocked by preflight"):
        controller.start_generation(app)
    assert app.current_run_id is None
    assert composition.service.hosts(project_id).get_plan(episode_id) is None


def test_generation_monitor_background_run_exposes_planning_failure(tmp_path: Path) -> None:
    composition = composition_with_empty_planning_output(tmp_path)
    project_id, episode_id = ready_episode(composition)
    run = composition.create_generation_run(project_id, episode_id)

    def run_from_monitor(run_id, progress) -> None:
        composition.run_generation(project_id, run_id, progress=progress)

    monitor = GenerationMonitorController(runner=run_from_monitor)
    app = TuiAppStub(
        composition=composition,
        preflight_controller=PreflightController(ffmpeg_executable=fake_ffmpeg(tmp_path)),
        generation_monitor_controller=monitor,
        current_project_id=project_id,
        current_project_name="Follow-up planning",
        current_episode_id=episode_id,
        current_run_id=run.id,
    )

    with pytest.raises(ValueError, match=EMPTY_SEGMENTS):
        asyncio.run(monitor.run(run.id))

    failed = composition.generation_run_repository(project_id).get(run.id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.stage == "planning"
    assert failed.failure_message is not None
    assert "non-empty segments" in failed.failure_message
    assert monitor.snapshot(app).run == failed
    assert any(
        event.operation == "planning" and event.state == "failed" for event in monitor.events
    )


def composition_with_missing_planning_model(tmp_path: Path) -> ProductionComposition:
    return configured_composition(tmp_path, "fake-v1", assignment_model="missing-v1")


def composition_with_empty_planning_output(tmp_path: Path) -> ProductionComposition:
    return configured_composition(tmp_path, "bad-v1")


def configured_composition(
    tmp_path: Path,
    provider_model: str,
    *,
    assignment_model: str | None = None,
) -> ProductionComposition:
    model = assignment_model or provider_model
    data_dir = tmp_path / f"data-cross-surface-{provider_model}-{model}"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model=provider_model),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={role.value: f"planner:{model}" for role in ModelRole},
        )
    )
    return ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )


def ready_episode(composition: ProductionComposition) -> tuple[str, str]:
    project = composition.service.create_project("Follow-up planning")
    composition.service.add_pasted_source(project.id, "Source", "Planning failure surface.")
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


def fake_ffmpeg(tmp_path: Path) -> Path:
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake", encoding="utf-8")
    return ffmpeg
