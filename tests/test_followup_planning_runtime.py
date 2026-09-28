from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.ffmpeg import FFmpegConfig
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.llm import FakeLLMProvider, LLMProvider, LLMRequest, LLMResponse
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight import PreflightBlockedError
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


def test_pipeline_auto_planning_uses_configured_episode_planning_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ffmpeg_detect(monkeypatch, _fake_ffmpeg_executable(tmp_path))
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
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake", encoding="utf-8")
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


def _patch_ffmpeg_detect(monkeypatch: pytest.MonkeyPatch, executable: Path) -> None:
    monkeypatch.setattr(
        FFmpegConfig,
        "detect",
        classmethod(lambda cls, configured=None: cls(executable)),
    )


def _fake_ffmpeg_executable(tmp_path: Path) -> Path:
    executable = tmp_path / "ffmpeg"
    executable.write_text(
        r"""#!/usr/bin/env python3
import io
import sys
import wave

payload = sys.stdin.buffer.read()
args = sys.argv[1:]
try:
    first_format = args[args.index('-f') + 1]
except (ValueError, IndexError):
    sys.exit(2)

if first_format == 'wav':
    try:
        with wave.open(io.BytesIO(payload), 'rb') as wav:
            source_rate = wav.getframerate()
            frame_count = wav.getnframes()
    except (EOFError, wave.Error):
        sys.exit(1)
elif first_format == 's16le':
    try:
        source_rate = int(args[args.index('-ar') + 1])
        channels = int(args[args.index('-ac') + 1])
    except (ValueError, IndexError):
        sys.exit(2)
    frame_size = channels * 2
    if not payload or len(payload) % frame_size != 0:
        sys.exit(1)
    frame_count = len(payload) // frame_size
else:
    sys.exit(2)

target_frames = max(1, round(frame_count * 24000 / source_rate))
sys.stdout.buffer.write(b'\x00\x00' * target_frames)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable
