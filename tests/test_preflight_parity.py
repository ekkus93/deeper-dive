from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.llm import FakeLLMProvider, ProviderHealth
from deeper_dive.preflight import PreflightReport
from deeper_dive.preflight_screen import PreflightApp, PreflightController
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.episode_repositories import HostProfileRecord
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class UnhealthyLLM(FakeLLMProvider):
    def health(self) -> ProviderHealth:
        return ProviderHealth(False, "llm offline")


class UnhealthyTTS(FakeTTSProvider):
    def health(self) -> ProviderHealth:
        return ProviderHealth(False, "tts offline")


@dataclass(slots=True)
class Scenario:
    expected_code: str | None
    defaults: dict[str, str]
    llm_scope: str | None = "local"
    tts_scope: str | None = "local"
    tts_provider: str = "speech"
    tts_voice: str = "voice-a"
    unhealthy_llm: bool = False
    unhealthy_tts: bool = False


@dataclass(slots=True)
class AppStub(PreflightApp):
    service: object
    provider_controller: ProviderController
    preflight_controller: PreflightController
    current_project_id: str | None
    current_project_name: str | None
    current_episode_id: str | None
    current_run_id: str | None = None

    def action_navigate(self, destination: str) -> None:
        _ = destination


@pytest.mark.parametrize(
    "scenario",
    (
        Scenario(None, {"local_only": "true"}),
        Scenario(
            "llm_assignment",
            {"host_generation": "missing:fake-v1", "local_only": "true"},
        ),
        Scenario(
            "llm_assignment",
            {"host_generation": "planner:missing-model", "local_only": "true"},
        ),
        Scenario("tts_assignment", {"local_only": "true"}, tts_provider="missing"),
        Scenario("tts_assignment", {"local_only": "true"}, tts_voice="missing"),
        Scenario("llm_unhealthy", {"local_only": "true"}, unhealthy_llm=True),
        Scenario("tts_unhealthy", {"local_only": "true"}, unhealthy_tts=True),
        Scenario("local_only_violation", {"local_only": "true"}, llm_scope="remote"),
        Scenario("local_only_violation", {"local_only": "true"}, tts_scope="remote"),
    ),
)
def test_cli_and_tui_preflight_share_provider_parity_matrix(
    tmp_path: Path,
    scenario: Scenario,
) -> None:
    composition, app, ffmpeg = _app(tmp_path, scenario)

    reports = _reports(composition, app, ffmpeg)

    for report in reports:
        codes = {issue.code for issue in report.blockers}
        if scenario.expected_code is None:
            assert report.ready
        else:
            assert scenario.expected_code in codes


def _reports(
    composition: ProductionComposition,
    app: AppStub,
    ffmpeg: Path,
) -> tuple[PreflightReport, PreflightReport]:
    tui_report = app.preflight_controller.build(app).report
    cli_report = composition.preflight_service.check(
        assignments=composition.effective_model_role_assignments_for_episode(
            app.current_project_id or "",
            app.current_episode_id or "",
        )[0],
        hosts=(),
        source_count=0,
        indexed_source_count=0,
        target_minutes=1,
        ffmpeg_executable=ffmpeg,
    )
    cli_report = composition.preflight_controller._shared_generation_start(app).preflight(  # type: ignore[union-attr]
        app.current_project_id or "",
        app.current_episode_id or "",
    )
    return cli_report, tui_report


def _app(tmp_path: Path, scenario: Scenario) -> tuple[ProductionComposition, AppStub, Path]:
    data_dir = tmp_path / "data"
    defaults = {
        "episode_planning": "planner:fake-v1",
        "host_generation": "planner:fake-v1",
        **scenario.defaults,
    }
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(
                    provider_type="fake",
                    default_model="fake-v1",
                    network_scope=scenario.llm_scope,
                ),
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    network_scope=scenario.tts_scope,
                ),
            },
            defaults=defaults,
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    if scenario.unhealthy_llm:
        composition.provider_controller.llm_registry.register(
            UnhealthyLLM(provider_id="planner", model="fake-v1")
        )
    if scenario.unhealthy_tts:
        composition.provider_controller.tts_providers["speech"] = UnhealthyTTS(
            provider_id="speech"
        )

    project = composition.service.create_project("Preflight parity")
    composition.service.add_pasted_source(project.id, "Source", "hello world\n\nsource text")
    hosts = composition.service.hosts(project.id)
    host = HostProfileRecord(
        id="host-1",
        project_id=project.id,
        display_name="Host",
        tts_provider=scenario.tts_provider,
        tts_voice=scenario.tts_voice,
    )
    hosts.create_host(host)
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Episode",
            target_duration_seconds=1200,
            host_ids=(host.id,),
        ),
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake")
    controller = PreflightController(ffmpeg_executable=ffmpeg)
    app = AppStub(
        service=composition.service,
        provider_controller=composition.provider_controller,
        preflight_controller=controller,
        current_project_id=project.id,
        current_project_name=project.name,
        current_episode_id=episode.id,
    )
    return composition, app, ffmpeg
