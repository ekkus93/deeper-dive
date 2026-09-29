from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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


class UnhealthyLLM(FakeLLMProvider):
    def health(self) -> ProviderHealth:
        return ProviderHealth(False, "llm offline")


class UnhealthyTTS(FakeTTSProvider):
    def health(self) -> ProviderHealth:
        return ProviderHealth(False, "tts offline")


class ExplodingTTS(FakeTTSProvider):
    def synthesize(self, request):  # type: ignore[no-untyped-def]
        _ = request
        raise AssertionError("preflight must not invoke TTS synthesis")


@dataclass(slots=True)
class AppStub:
    service: DeeperDiveService
    composition: ProductionComposition
    provider_controller: ProviderController
    preflight_controller: PreflightController
    current_project_id: str | None
    current_project_name: str | None
    current_episode_id: str | None
    current_run_id: str | None = None

    def action_navigate(self, destination: str) -> None:
        _ = destination


def test_cli_and_tui_preflight_accept_valid_local_routes(tmp_path: Path) -> None:
    _assert_parity(tmp_path, expected_code=None, defaults={"local_only": "true"})


def test_cli_and_tui_preflight_reject_missing_llm_provider(tmp_path: Path) -> None:
    _assert_parity(
        tmp_path,
        expected_code="llm_assignment",
        defaults={"host_generation": "missing:fake-v1", "local_only": "true"},
    )


def test_cli_and_tui_preflight_reject_unavailable_llm_model(tmp_path: Path) -> None:
    _assert_parity(
        tmp_path,
        expected_code="llm_assignment",
        defaults={"host_generation": "planner:missing-model", "local_only": "true"},
    )


def test_cli_and_tui_preflight_reject_missing_tts_provider(tmp_path: Path) -> None:
    _assert_parity(
        tmp_path,
        expected_code="tts_assignment",
        defaults={"local_only": "true"},
        tts_provider="missing",
    )


def test_cli_and_tui_preflight_reject_missing_tts_voice(tmp_path: Path) -> None:
    _assert_parity(
        tmp_path,
        expected_code="tts_assignment",
        defaults={"local_only": "true"},
        tts_voice="missing",
    )


def test_cli_and_tui_preflight_reject_unhealthy_llm_provider(tmp_path: Path) -> None:
    _assert_parity(
        tmp_path,
        expected_code="llm_unhealthy",
        defaults={"local_only": "true"},
        unhealthy_llm=True,
    )


def test_cli_and_tui_preflight_reject_unhealthy_tts_provider(tmp_path: Path) -> None:
    _assert_parity(
        tmp_path,
        expected_code="tts_unhealthy",
        defaults={"local_only": "true"},
        unhealthy_tts=True,
    )


def test_cli_and_tui_preflight_reject_local_only_remote_llm(tmp_path: Path) -> None:
    _assert_parity(
        tmp_path,
        expected_code="local_only_violation",
        defaults={"local_only": "true"},
        llm_scope="remote",
    )


def test_cli_and_tui_preflight_reject_local_only_remote_tts(tmp_path: Path) -> None:
    _assert_parity(
        tmp_path,
        expected_code="local_only_violation",
        defaults={"local_only": "true"},
        tts_scope="remote",
    )


def test_cli_and_tui_preflight_reject_non_wav_tts_before_synthesis(
    tmp_path: Path,
) -> None:
    composition, app = _app(
        tmp_path,
        defaults={"local_only": "true"},
        llm_scope="local",
        tts_scope="local",
        tts_provider="speech",
        tts_voice="voice-a",
        tts_response_format="mp3",
        unhealthy_llm=False,
        unhealthy_tts=False,
    )
    composition.provider_controller.tts_providers["speech"] = ExplodingTTS(provider_id="speech")
    cli_report, tui_report = _reports(composition, app)
    cli_codes = _blocker_codes(cli_report)
    tui_codes = _blocker_codes(tui_report)

    assert cli_codes == tui_codes
    assert "tts_format_unsupported" in cli_codes


def _assert_parity(
    tmp_path: Path,
    *,
    expected_code: str | None,
    defaults: dict[str, str],
    llm_scope: Literal["local", "remote"] | None = "local",
    tts_scope: Literal["local", "remote"] | None = "local",
    tts_provider: str = "speech",
    tts_voice: str = "voice-a",
    tts_response_format: str = "wav",
    unhealthy_llm: bool = False,
    unhealthy_tts: bool = False,
) -> None:
    composition, app = _app(
        tmp_path,
        defaults=defaults,
        llm_scope=llm_scope,
        tts_scope=tts_scope,
        tts_provider=tts_provider,
        tts_voice=tts_voice,
        tts_response_format=tts_response_format,
        unhealthy_llm=unhealthy_llm,
        unhealthy_tts=unhealthy_tts,
    )
    cli_report, tui_report = _reports(composition, app)
    cli_codes = _blocker_codes(cli_report)
    tui_codes = _blocker_codes(tui_report)

    assert cli_codes == tui_codes
    if expected_code is None:
        assert cli_report.ready
        assert tui_report.ready
    else:
        assert expected_code in cli_codes


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


def _app(
    tmp_path: Path,
    *,
    defaults: dict[str, str],
    llm_scope: Literal["local", "remote"] | None,
    tts_scope: Literal["local", "remote"] | None,
    tts_provider: str,
    tts_voice: str,
    tts_response_format: str,
    unhealthy_llm: bool,
    unhealthy_tts: bool,
) -> tuple[ProductionComposition, AppStub]:
    data_dir = tmp_path / "data"
    user_defaults = {
        "episode_planning": "planner:fake-v1",
        "host_generation": "planner:fake-v1",
        **defaults,
    }
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(
                    provider_type="fake",
                    default_model="fake-v1",
                    network_scope=llm_scope,
                ),
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    network_scope=tts_scope,
                    response_format=tts_response_format,
                ),
            },
            defaults=user_defaults,
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    if unhealthy_llm:
        unhealthy = UnhealthyLLM(provider_id="planner", model="fake-v1")
        composition.provider_controller.llm_registry.register(unhealthy)
    if unhealthy_tts:
        composition.provider_controller.tts_providers["speech"] = UnhealthyTTS(provider_id="speech")

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
        tts_provider=tts_provider,
        tts_voice=tts_voice,
    )
    hosts.create_host(host)
    configurations = EpisodeConfigurationService(composition.database_for_project(project.id))
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
        composition=composition,
        provider_controller=composition.provider_controller,
        preflight_controller=controller,
        current_project_id=project.id,
        current_project_name=project.name,
        current_episode_id=episode.id,
    )
    return composition, app
