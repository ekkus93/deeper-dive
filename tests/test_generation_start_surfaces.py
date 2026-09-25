from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from deeper_dive import cli as cli_module
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.pipeline import PipelineResult
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


@dataclass(slots=True)
class _PreflightApp:
    service: DeeperDiveService
    provider_controller: ProviderController
    preflight_controller: PreflightController
    current_project_id: str | None
    current_project_name: str | None
    current_episode_id: str | None
    current_run_id: str | None = None

    def action_navigate(self, destination: str) -> None:
        _ = destination


def _json_call(args: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def _fake_ffmpeg(tmp_path: Path) -> Path:
    executable = tmp_path / "ffmpeg"
    executable.write_text("fake", encoding="utf-8")
    return executable


def _ready_composition(tmp_path: Path) -> tuple[ProductionComposition, str, str]:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={
                "episode_planning": "planner:fake-v1",
                "host_generation": "planner:fake-v1",
            },
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Run selection surfaces")
    composition.service.add_pasted_source(project.id, "Fixture source", "Indexed content.")
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Run selection episode",
            focus="Duplicate start handling",
            target_duration_seconds=900,
            host_ids=(host.id,),
        ),
    )
    return composition, project.id, episode.id


def _hold_generation(
    composition: ProductionComposition,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run_generation(
        project_id: str,
        run_id: str,
        *,
        progress: object | None = None,
    ) -> PipelineResult:
        _ = progress
        run = composition.generation_run_repository(project_id).get(run_id)
        assert run is not None
        return PipelineResult(run, (), ())

    monkeypatch.setattr(composition, "run_generation", run_generation)


def _patch_cli_build(
    composition: ProductionComposition,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )


def _patch_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeper_dive.preflight.FFmpegConfig.detect",
        staticmethod(lambda executable=None: executable or Path("/fake/ffmpeg")),
    )


def test_repeated_cli_generate_reuses_active_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition, project_id, episode_id = _ready_composition(tmp_path)
    _hold_generation(composition, monkeypatch)
    _patch_cli_build(composition, monkeypatch)
    _patch_ffmpeg(monkeypatch)
    base = ["--data-dir", str(composition.service.workspaces.data_dir), "--json", "episode"]

    first = _json_call([*base, "generate", project_id, episode_id], capsys)
    second = _json_call([*base, "generate", project_id, episode_id], capsys)
    status = _json_call([*base, "status", project_id, episode_id], capsys)

    assert second["id"] == first["id"]
    assert first["state"] == "pending"
    assert second["state"] == "pending"
    assert status["run"]["id"] == first["id"]


def test_repeated_tui_generate_reuses_active_run(tmp_path: Path) -> None:
    composition, project_id, episode_id = _ready_composition(tmp_path)
    controller = PreflightController(ffmpeg_executable=_fake_ffmpeg(tmp_path))
    app = _PreflightApp(
        service=composition.service,
        provider_controller=composition.provider_controller,
        preflight_controller=controller,
        current_project_id=project_id,
        current_project_name="Run selection surfaces",
        current_episode_id=episode_id,
    )

    first = controller.start_generation(app)
    second = controller.start_generation(app)

    assert second.id == first.id
    assert app.current_run_id == first.id
    assert composition.generation_run_repository(project_id).latest_for_episode(episode_id) == first


def test_mixed_cli_then_tui_generate_reuses_active_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition, project_id, episode_id = _ready_composition(tmp_path)
    _hold_generation(composition, monkeypatch)
    _patch_cli_build(composition, monkeypatch)
    _patch_ffmpeg(monkeypatch)
    base = ["--data-dir", str(composition.service.workspaces.data_dir), "--json", "episode"]
    cli_run = _json_call([*base, "generate", project_id, episode_id], capsys)
    controller = PreflightController(ffmpeg_executable=_fake_ffmpeg(tmp_path))
    app = _PreflightApp(
        service=composition.service,
        provider_controller=composition.provider_controller,
        preflight_controller=controller,
        current_project_id=project_id,
        current_project_name="Run selection surfaces",
        current_episode_id=episode_id,
    )

    tui_run = controller.start_generation(app)

    assert tui_run.id == cli_run["id"]
    assert app.current_run_id == cli_run["id"]
