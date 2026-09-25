from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.preflight import PreflightBlockedError, PreflightReport
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


def _fake_ffmpeg(tmp_path: Path, *, available: bool = True) -> Path:
    executable = tmp_path / "ffmpeg"
    if available:
        executable.write_text("fake", encoding="utf-8")
    return executable


def _composition(
    tmp_path: Path,
    *,
    defaults: dict[str, str] | None = None,
) -> ProductionComposition:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults=defaults
            or {
                "episode_planning": "planner:fake-v1",
                "host_generation": "planner:fake-v1",
            },
        )
    )
    return ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )


def _episode(
    composition: ProductionComposition,
    *,
    source: bool = True,
    indexed: bool = True,
    host: bool = True,
    tts: bool = True,
) -> tuple[str, str]:
    project = composition.service.create_project("Preflight matrix")
    if source:
        record = composition.service.add_pasted_source(
            project.id,
            "Fixture source",
            "Deterministic indexed source text.",
        )
        if not indexed:
            database = composition.database_for_project(project.id)
            with database.transaction() as connection:
                connection.execute("DELETE FROM source_chunks WHERE source_id=?", (record.id,))
    host_ids: tuple[str, ...] = ()
    if host:
        profile = create_host_from_preset("curious_explainer", project.id)
        if tts:
            profile.tts_provider = "speech"
            profile.tts_voice = "voice-a"
        composition.service.hosts(project.id).create_host(profile.to_record())
        host_ids = (profile.id,)
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Matrix episode",
            focus="Readiness matrix",
            target_duration_seconds=900,
            host_ids=host_ids,
        ),
    )
    return project.id, episode.id


def _codes(report: PreflightReport) -> set[str]:
    return {issue.code for issue in report.blockers}


@pytest.mark.parametrize(
    ("case", "episode_kwargs", "defaults", "ffmpeg_available", "expected_codes"),
    [
        ("missing_sources", {"source": False}, None, True, {"sources_missing"}),
        ("unindexed_sources", {"indexed": False}, None, True, {"sources_unindexed"}),
        ("missing_hosts", {"host": False}, None, True, {"hosts_missing"}),
        ("missing_tts", {"tts": False}, None, True, {"tts_assignment"}),
        (
            "missing_host_generation_assignment",
            {},
            {"episode_planning": "planner:fake-v1"},
            True,
            {"llm_assignment"},
        ),
        (
            "invalid_provider_assignment",
            {},
            {
                "episode_planning": "planner:fake-v1",
                "host_generation": "ghost:fake-v1",
            },
            True,
            {"llm_assignment"},
        ),
        (
            "unsupported_model_assignment",
            {},
            {
                "episode_planning": "planner:fake-v1",
                "host_generation": "planner:missing-model",
            },
            True,
            {"llm_assignment"},
        ),
        ("missing_ffmpeg", {}, None, False, {"ffmpeg_unavailable"}),
    ],
)
def test_shared_cli_tui_generation_start_blocker_matrix(
    tmp_path: Path,
    case: str,
    episode_kwargs: dict[str, bool],
    defaults: dict[str, str] | None,
    ffmpeg_available: bool,
    expected_codes: set[str],
) -> None:
    _ = case
    composition = _composition(tmp_path, defaults=defaults)
    project_id, episode_id = _episode(composition, **episode_kwargs)
    ffmpeg = _fake_ffmpeg(tmp_path, available=ffmpeg_available)
    controller = PreflightController(ffmpeg_executable=ffmpeg)
    app = _PreflightApp(
        service=composition.service,
        provider_controller=composition.provider_controller,
        preflight_controller=controller,
        current_project_id=project_id,
        current_project_name="Preflight matrix",
        current_episode_id=episode_id,
    )

    cli_report = GenerationStartService(composition, ffmpeg_executable=ffmpeg).preflight(
        project_id,
        episode_id,
    )
    tui_report = controller.build(app).report

    assert expected_codes <= _codes(cli_report)
    assert _codes(tui_report) == _codes(cli_report)


def test_shared_generation_start_blocks_before_creating_run(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    project_id, episode_id = _episode(composition, source=False)
    ffmpeg = _fake_ffmpeg(tmp_path)

    with pytest.raises(PreflightBlockedError, match="generation blocked by preflight"):
        GenerationStartService(composition, ffmpeg_executable=ffmpeg).start(project_id, episode_id)

    assert composition.generation_run_repository(project_id).latest_for_episode(episode_id) is None
