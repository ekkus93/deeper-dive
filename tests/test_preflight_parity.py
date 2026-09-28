from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.llm import FakeLLMProvider, ProviderHealth
from deeper_dive.preflight import PreflightReport
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.episode_repositories import HostProfileRecord
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore

NetworkScope = Literal["local", "remote"] | None


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
    llm_scope: NetworkScope = "local"
    tts_scope: NetworkScope = "local"
    tts_provider: str = "speech"
    tts_voice: str = "voice-a"
    unhealthy_llm: bool = False
    unhealthy_tts: bool = False


@dataclass(slots=True)
class AppStub:
    service: DeeperDiveService
    provider_controller: ProviderController
    preflight_controller: PreflightController
    current_project_id: str | None
    current_project_name: str | None
    current_episode_id: str | None
    current_run_id: str | None = None

    def action_navigate(self, destination: str) -> None:
        _ = destination


SCENARIOS = (
    Scenario(
        expected_code=None,
        defaults={
            "local_only": "true",
        },
    ),
    Scenario(
        expected_code="llm_assignment",
        defaults={
            "host_generation": "missing:fake-v1",
            "local_only": "true",
        },
    ),
    Scenario(
        expected_code="llm_assignment",
        defaults={
            "host_generation": "planner:missing-model",
            "local_only": "true",
        },
    ),
    Scenario(
        expected_code="tts_assignment",
        defaults={
            "local_only": "true",
        },
        tts_provider="missing",
    ),
    Scenario(
        expected_code="tts_assignment",
        defaults={
            "local_only": "true",
        },
        tts_voice="missing",
    ),
    Scenario(
        expected_code="llm_unhealthy",
        defaults={
            "local_only": "true",
        },
        unhealthy_llm=True,
    ),
    Scenario(
        expected_code="tts_unhealthy",
        defaults={
            "local_only": "true",
        },
        unhealthy_tts=True,
    ),
    Scenario(
        expected_code="local_only_violation",
        defaults={
            "local_only": "true",
        },
        llm_scope="remote",
    ),
    Scenario(
        expected_code="local_only_violation",
        defaults={
            "local_only": "true",
        },
        tts_scope="remote",
    ),
)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_cli_and_tui_preflight_share_provider_parity_matrix(
    tmp_path: Path,
    scenario: Scenario,
) -> None:
    composition, app = _app(tmp_path, scenario)
    cli_report, tui_report = _reports(composition, app)

    cli_codes = _blocker_codes(cli_report)
    tui_codes = _blocker_codes(tui_report)

    assert cli_codes == tui_codes
    if scenario.expected_code is None:
        assert cli_report.ready
        assert tui_report.ready
    else:
        assert scenario.expected_code in cli_codes


def _blocker_codes(report: PreflightReport) -> set[str]:
    return {issue.code for issue in report.blockers}


def _reports(
    composition: ProductionComposition,
    app: AppStub,
) -> tuple[PreflightReport, PreflightReport]:
    starter = app.preflight_controller._shared_generation_start(app)
    assert starter is not None
    cli_report = starter.preflight(
        app.current_project_id or "",
        app.current_episode_id or "",
    )
    tui_report = app.preflight_controller.build(app).report
    return cli_report, tui_report


def _app(tmp_path: Path, scenario: Scenario) -> tuple[ProductionComposition, AppStub]:
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
        unhealthy_llm = UnhealthyLLM(
            provider_id="planner",
            model="fake-v1",
        )
        composition.provider_controller.llm_registry.register(unhealthy_llm)
    if scenario.unhealthy_tts:
        unhealthy_tts = UnhealthyTTS(
            provider_id="speech",
        )
        composition.provider_controller.tts_providers["speech"] = unhealthy_tts

    project = composition.service.create_project("Preflight parity")
    composition.service.add_pasted_source(
        project.id,
        "Source",
        "hello world\n\nsource text",
    )
    hosts = composition.service.hosts(project.id)
    host = HostProfileRecord(
        id="host-1",
        project_id=project.id,
        display_name="Host",
        tts_provider=scenario.tts_provider,
        tts_voice=scenario.tts_voice,
    )
    hosts.create_host(host)
    configurations = EpisodeConfigurationService(
        composition.database_for_project(project.id)
    )
    episode = configurations.create(
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
    return composition, app
