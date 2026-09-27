from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from deeper_dive import cli
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.generation_monitor import GenerationMonitorController
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.llm import FakeLLMProvider, LLMProvider, LLMRequest, LLMResponse
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight import PreflightBlockedError
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class _ExplodingPlanningProvider(FakeLLMProvider):
    def generate(self, request: LLMRequest) -> LLMResponse:
        _ = request
        raise RuntimeError("synthetic planning provider failure")


class _PlanningResponseFactory(ProviderFactory):
    def _llm(self, kind: str, config: ProviderConfig) -> LLMProvider:
        if kind == "fake" and config.default_model == "bad-v1":
            return FakeLLMProvider(model="bad-v1", response=json.dumps({"segments": []}))
        if kind == "fake" and config.default_model == "invalid-json-v1":
            return FakeLLMProvider(model="invalid-json-v1", response="not-json")
        if kind == "fake" and config.default_model == "explode-v1":
            return _ExplodingPlanningProvider(model="explode-v1")
        return super()._llm(kind, config)


@dataclass(slots=True)
class _TuiAppStub:
    composition: ProductionComposition
    preflight_controller: PreflightController
    generation_monitor_controller: GenerationMonitorController | None = None
    current_project_id: str | None = None
    current_project_name: str | None = None
    current_episode_id: str | None = None
    current_run_id: str | None = None
    last_navigation: str | None = None

    @property
    def service(self) -> Any:
        return self.composition.service

    @property
    def provider_controller(self) -> Any:
        return self.composition.provider_controller

    def action_navigate(self, destination: str) -> None:
        self.last_navigation = destination


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
    composition = _composition_with_planning_model(tmp_path, "bad-v1")
    project_id, episode_id = _ready_episode(composition)
    run = composition.create_generation_run(project_id, episode_id)

    with pytest.raises(ValueError, match="episode plan must contain a non-empty segments list"):
        composition.run_generation(project_id, run.id)

    _assert_failed_planning(
        composition,
        project_id,
        episode_id,
        run.id,
        "non-empty segments",
    )


def test_pipeline_auto_planning_fails_durably_on_invalid_json(
    tmp_path: Path,
) -> None:
    composition = _composition_with_planning_model(tmp_path, "invalid-json-v1")
    project_id, episode_id = _ready_episode(composition)
    run = composition.create_generation_run(project_id, episode_id)

    with pytest.raises(json.JSONDecodeError):
        composition.run_generation(project_id, run.id)

    _assert_failed_planning(
        composition,
        project_id,
        episode_id,
        run.id,
        "Expecting value",
    )


def test_pipeline_auto_planning_fails_durably_on_provider_exception(
    tmp_path: Path,
) -> None:
    composition = _composition_with_planning_model(tmp_path, "explode-v1")
    project_id, episode_id = _ready_episode(composition)
    run = composition.create_generation_run(project_id, episode_id)

    with pytest.raises(RuntimeError, match="synthetic planning provider failure"):
        composition.run_generation(project_id, run.id)

    _assert_failed_planning(
        composition,
        project_id,
        episode_id,
        run.id,
        "synthetic planning provider failure",
    )


def test_pipeline_auto_planning_fails_durably_on_unknown_provider(
    tmp_path: Path,
) -> None:
    composition = _composition_with_planning_model(
        tmp_path,
        "fake-v1",
        assignment_provider="missing",
    )
    project_id, episode_id = _ready_episode(composition)
    run = composition.create_generation_run(project_id, episode_id)

    with pytest.raises(ValueError, match="unknown provider 'missing' for episode_planning"):
        composition.run_generation(project_id, run.id)

    _assert_failed_planning(
        composition,
        project_id,
        episode_id,
        run.id,
        "unknown provider 'missing'",
    )


def test_generation_start_blocks_unavailable_planning_model(tmp_path: Path) -> None:
    composition = _composition_with_planning_model(
        tmp_path,
        "fake-v1",
        assignment_model="missing-v1",
    )
    project_id, episode_id = _ready_episode(composition)
    ffmpeg = _fake_ffmpeg(tmp_path)
    starter = GenerationStartService(composition, ffmpeg_executable=ffmpeg)

    report = starter.preflight(project_id, episode_id)

    assert not report.ready
    assert any(
        "model 'missing-v1' is unavailable from provider 'planner'" in blocker.message
        for blocker in report.blockers
    )
    with pytest.raises(PreflightBlockedError, match="generation blocked by preflight"):
        starter.start(project_id, episode_id)
    assert composition.service.hosts(project_id).get_plan(episode_id) is None


def test_cli_episode_generate_exposes_planning_preflight_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    composition = _composition_with_planning_model(
        tmp_path,
        "fake-v1",
        assignment_model="missing-v1",
    )
    project_id, episode_id = _ready_episode(composition)

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
    assert "model 'missing-v1' is unavailable from provider 'planner'" in captured.err
    assert composition.service.hosts(project_id).get_plan(episode_id) is None


def test_tui_generate_controller_exposes_same_planning_preflight_failure(
    tmp_path: Path,
) -> None:
    composition = _composition_with_planning_model(
        tmp_path,
        "fake-v1",
        assignment_model="missing-v1",
    )
    project_id, episode_id = _ready_episode(composition)
    controller = PreflightController(ffmpeg_executable=_fake_ffmpeg(tmp_path))
    app = _TuiAppStub(
        composition=composition,
        preflight_controller=controller,
        current_project_id=project_id,
        current_project_name="Follow-up planning",
        current_episode_id=episode_id,
    )

    presentation = controller.build(app)

    assert not presentation.report.ready
    assert any(
        "model 'missing-v1' is unavailable from provider 'planner'" in blocker.message
        for blocker in presentation.report.blockers
    )
    with pytest.raises(PreflightBlockedError, match="generation blocked by preflight"):
        controller.start_generation(app)
    assert app.current_run_id is None
    assert composition.service.hosts(project_id).get_plan(episode_id) is None


def test_generation_monitor_background_run_exposes_planning_failure(
    tmp_path: Path,
) -> None:
    composition = _composition_with_planning_model(tmp_path, "bad-v1")
    project_id, episode_id = _ready_episode(composition)
    run = composition.create_generation_run(project_id, episode_id)

    def _run_from_monitor(run_id: str, progress: Any) -> None:
        composition.run_generation(project_id, run_id, progress=progress)

    monitor = GenerationMonitorController(runner=_run_from_monitor)
    app = _TuiAppStub(
        composition=composition,
        preflight_controller=PreflightController(ffmpeg_executable=_fake_ffmpeg(tmp_path)),
        generation_monitor_controller=monitor,
        current_project_id=project_id,
        current_project_name="Follow-up planning",
        current_episode_id=episode_id,
        current_run_id=run.id,
    )

    with pytest.raises(ValueError, match="episode plan must contain a non-empty segments list"):
        asyncio.run(monitor.run(run.id))

    failed = composition.generation_run_repository(project_id).get(run.id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.stage == "planning"
    assert failed.failure_message is not None
    assert "non-empty segments" in failed.failure_message
    snapshot = monitor.snapshot(app)
    assert snapshot.run == failed
    assert any(event.operation == "planning" and event.state == "failed" for event in monitor.events)


def _assert_failed_planning(
    composition: ProductionComposition,
    project_id: str,
    episode_id: str,
    run_id: str,
    expected_message: str,
) -> None:
    failed = composition.generation_run_repository(project_id).get(run_id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.stage == "planning"
    assert failed.failure_message is not None
    assert expected_message in failed.failure_message
    assert composition.service.hosts(project_id).get_plan(episode_id) is None


def _composition_with_two_planners(tmp_path: Path) -> ProductionComposition:
    data_dir = tmp_path / "data-two-planners"
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


def _composition_with_planning_model(
    tmp_path: Path,
    provider_model: str,
    *,
    assignment_provider: str = "planner",
    assignment_model: str | None = None,
) -> ProductionComposition:
    data_dir = tmp_path / f"data-{provider_model}-{assignment_provider}-{assignment_model}"
    model = assignment_model or provider_model
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model=provider_model),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={role.value: f"{assignment_provider}:{model}" for role in ModelRole},
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


def _fake_ffmpeg(tmp_path: Path) -> Path:
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake", encoding="utf-8")
    return ffmpeg
