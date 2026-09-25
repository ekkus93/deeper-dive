# fmt: off
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.generation_monitor import GenerationMonitorScreen
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry, ProviderHealth
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight import PreflightEstimate, PreflightReport
from deeper_dive.preflight_screen import (
    PreflightController,
    PreflightPresentation,
    PreflightScreen,
)
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.provider_tui import ProviderController
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tui import (
    GLOBAL_SCREENS,
    PROJECT_SCREENS,
    DeeperDiveApp,
    HomeProjectsScreen,
    SourcesScreen,
)
from deeper_dive.user_config import UserConfig, UserConfigStore


def test_shell_navigates_all_destinations(tmp_path: Path) -> None:
    asyncio.run(_navigate_all_destinations(tmp_path))


async def _navigate_all_destinations(tmp_path: Path) -> None:
    app = DeeperDiveApp(_service(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        assert app.screen.id == "screen-home"
        for destination in (*GLOBAL_SCREENS[1:], *PROJECT_SCREENS):
            await pilot.press(*_shortcut(destination))
            await pilot.pause()
            assert app.screen.id == f"screen-{destination}"
            assert app.screen.query_one("#screen-status") is not None


def test_shell_runs_at_minimum_terminal_size(tmp_path: Path) -> None:
    asyncio.run(_run_at_minimum_terminal_size(tmp_path))


async def _run_at_minimum_terminal_size(tmp_path: Path) -> None:
    app = DeeperDiveApp(_service(tmp_path))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("1")
        await pilot.pause()
        assert app.screen.id == "screen-sources"
        await pilot.press("h")
        await pilot.pause()
        assert app.screen.id == "screen-home"


def test_providers_tui_saves_extended_supported_fields(tmp_path: Path) -> None:
    asyncio.run(_providers_tui_saves_extended_supported_fields(tmp_path))


async def _providers_tui_saves_extended_supported_fields(tmp_path: Path) -> None:
    secret = "local-tts-secret-value"
    provider_controller = ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={"LOCAL_TTS_KEY": secret}),
    )
    app = DeeperDiveApp(_service(tmp_path), provider_controller=provider_controller)
    async with app.run_test(size=(120, 36)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = _providers(app)
        screen.query_one("#provider-name", Input).value = "speech"
        screen.query_one("#provider-type", Input).value = "openai-compatible-tts"
        screen.query_one("#provider-base-url", Input).value = "http://127.0.0.1:9000/v1"
        screen.query_one("#provider-default-model", Input).value = "local-tts"
        screen.query_one("#provider-credential-env", Input).value = "LOCAL_TTS_KEY"
        screen.query_one("#provider-timeout-seconds", Input).value = "12.5"
        screen.query_one("#provider-network-scope", Input).value = "local"
        screen.query_one("#provider-response-format", Input).value = "mp3"
        screen.query_one("#provider-voices", Input).value = "alice, bob, ,"

        screen.action_save()
        await pilot.pause()

        saved = provider_controller.config().providers["speech"]
        assert saved.base_url == "http://127.0.0.1:9000/v1"
        assert saved.default_model == "local-tts"
        assert saved.credential_env == "LOCAL_TTS_KEY"
        assert saved.timeout_seconds == 12.5
        assert saved.network_scope == "local"
        assert saved.response_format == "mp3"
        assert saved.voices == ("alice", "bob")
        assert tuple(voice.id for voice in provider_controller.tts("speech").voices()) == (
            "alice",
            "bob",
        )
        assert "Supported optional fields for openai-compatible-tts" in _text(
            screen, "#provider-details"
        )
        assert secret not in _text(screen, "#provider-details")
        assert secret not in _text(screen, "#screen-status")
        assert secret not in (tmp_path / "config.json").read_text(encoding="utf-8")


def test_providers_tui_ignores_unsupported_fields_per_adapter(tmp_path: Path) -> None:
    asyncio.run(_providers_tui_ignores_unsupported_fields_per_adapter(tmp_path))


async def _providers_tui_ignores_unsupported_fields_per_adapter(tmp_path: Path) -> None:
    provider_controller = ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ={}),
    )
    app = DeeperDiveApp(_service(tmp_path), provider_controller=provider_controller)
    async with app.run_test(size=(120, 36)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = _providers(app)
        screen.query_one("#provider-name", Input).value = "kitten-local"
        screen.query_one("#provider-type", Input).value = "kitten"
        screen.query_one("#provider-base-url", Input).value = "http://ignored.example/v1"
        screen.query_one("#provider-default-model", Input).value = "ignored-model"
        screen.query_one("#provider-credential-env", Input).value = "IGNORED_SECRET"
        screen.query_one("#provider-timeout-seconds", Input).value = "7"
        screen.query_one("#provider-network-scope", Input).value = "local"
        screen.query_one("#provider-response-format", Input).value = "mp3"
        screen.query_one("#provider-voices", Input).value = "ignored-voice"

        screen.action_save()
        await pilot.pause()

        saved = provider_controller.config().providers["kitten-local"]
        assert saved.provider_type == "kitten"
        assert saved.base_url is None
        assert saved.default_model is None
        assert saved.credential_env is None
        assert saved.timeout_seconds == 60.0
        assert saved.network_scope == "local"
        assert saved.response_format == "wav"
        assert saved.voices == ()
        details = _text(screen, "#provider-details")
        assert "Supported optional fields for kitten: network scope" in details
        assert "Ignored fields for kitten" in details
        assert "base URL" in details
        assert "credential environment variable name" in details


@pytest.mark.parametrize(
    ("name", "provider_type", "fields", "capability"),
    (
        (
            "openai-main",
            "openai",
            {"default_model": "gpt-test", "credential_env": "OPENAI_TEST_KEY"},
            "llm",
        ),
        (
            "ollama-local",
            "ollama",
            {"default_model": "qwen-test", "base_url": "http://127.0.0.1:11434"},
            "llm",
        ),
        (
            "compatible-local",
            "llama-server",
            {"default_model": "local-test", "base_url": "http://127.0.0.1:8080"},
            "llm",
        ),
        ("kitten-local", "kitten", {"network_scope": "local"}, "tts"),
        (
            "openai-speech",
            "openai-tts",
            {"default_model": "tts-test", "credential_env": "OPENAI_TEST_KEY"},
            "tts",
        ),
        (
            "compatible-speech",
            "openai-compatible-tts",
            {
                "base_url": "http://127.0.0.1:9000/v1",
                "default_model": "local-tts",
                "credential_env": "LOCAL_TTS_KEY",
                "response_format": "mp3",
                "voices": "voice-a, voice-b",
            },
            "tts",
        ),
        (
            "eleven-speech",
            "elevenlabs",
            {"default_model": "eleven-test", "credential_env": "ELEVEN_TEST_KEY"},
            "tts",
        ),
    ),
)
def test_providers_tui_save_reload_health_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    provider_type: str,
    fields: dict[str, str],
    capability: str,
) -> None:
    asyncio.run(
        _providers_tui_save_reload_health_matrix(
            tmp_path,
            monkeypatch,
            name,
            provider_type,
            fields,
            capability,
        )
    )


async def _providers_tui_save_reload_health_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    provider_type: str,
    fields: dict[str, str],
    capability: str,
) -> None:
    secrets = {
        "OPENAI_TEST_KEY": "openai-secret-value",
        "LOCAL_TTS_KEY": "local-secret-value",
        "ELEVEN_TEST_KEY": "eleven-secret-value",
    }
    provider_controller = ProviderController(
        UserConfigStore(tmp_path / "config.json"),
        LLMProviderRegistry(),
        {},
        provider_factory=ProviderFactory(environ=secrets),
    )
    app = DeeperDiveApp(_service(tmp_path), provider_controller=provider_controller)
    async with app.run_test(size=(120, 36)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = _providers(app)
        _set_provider_form(screen, name, provider_type, fields)

        screen.action_save()
        await pilot.pause()

        saved = provider_controller.config().providers[name]
        assert saved.provider_type == provider_type
        assert provider_controller.capability(provider_type) == capability
        if capability == "llm":
            provider = provider_controller.llm(name)
        else:
            provider = provider_controller.tts(name)
        assert provider.provider_id == name
        monkeypatch.setattr(provider, "health", lambda: ProviderHealth(True, "adapter-ready"))
        screen.action_health()
        await pilot.pause()
        status = _text(screen, "#screen-status")
        details = _text(screen, "#provider-details")
        persisted = (tmp_path / "config.json").read_text(encoding="utf-8")
        assert f"{name}: healthy - adapter-ready" in status
        assert f"Supported optional fields for {provider_type}" in details
        assert all(secret not in status for secret in secrets.values())
        assert all(secret not in details for secret in secrets.values())
        assert all(secret not in persisted for secret in secrets.values())


def test_home_projects_workflow_create_open_rename_delete_cancel(tmp_path: Path) -> None:
    asyncio.run(_home_projects_workflow(tmp_path))


async def _home_projects_workflow(tmp_path: Path) -> None:
    app = DeeperDiveApp(_service(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        home = _home(app)
        home.query_one("#new-project-name", Input).value = "Alpha"
        home.action_create_project()
        await pilot.pause()
        assert "Alpha" in _text(home, "#project-list")
        assert "sources 0" in _text(home, "#project-list")

        home.query_one("#rename-project-name", Input).value = "Beta"
        home.action_rename_selected()
        await pilot.pause()
        assert "Beta" in _text(home, "#project-list")

        home.action_open_selected()
        await pilot.pause()
        assert app.current_project_name == "Beta"
        assert app.screen.id == "screen-sources"

        app.action_navigate("home")
        await pilot.pause()
        home = _home(app)
        home.action_request_delete()
        home.action_cancel_delete()
        await pilot.pause()
        assert "Beta" in _text(home, "#project-list")
        assert "Delete cancelled" in _text(home, "#screen-status")

        home.action_request_delete()
        home.action_confirm_delete()
        await pilot.pause()
        assert "No projects yet" in _text(home, "#project-list")


def test_home_projects_surface_interrupted_run_state(tmp_path: Path) -> None:
    asyncio.run(_home_projects_interrupted_run_state(tmp_path))


async def _home_projects_interrupted_run_state(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Interrupted")
    timestamp = format_timestamp(service.clock.now())
    episode_id = str(new_episode_id())
    service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            created_at=timestamp,
            modified_at=timestamp,
        ),
        [],
    )
    service.runs(project.id).create(
        GenerationRunRecord(
            id=str(new_run_id()),
            episode_id=episode_id,
            stage="conversation",
            state="paused",
            created_at=timestamp,
            modified_at=timestamp,
            pause_requested=True,
        )
    )

    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)):
        assert "pause requested" in _text(_home(app), "#project-list")


def test_sources_tui_add_inspect_toggle_and_delete(tmp_path: Path) -> None:
    asyncio.run(_sources_tui_workflow(tmp_path))


async def _sources_tui_workflow(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Sources")
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("sources")
        await pilot.pause()
        sources = _sources(app)
        sources.query_one("#source-title", Input).value = "Notes"
        sources.query_one("#source-text", Input).value = "First line about evidence."
        sources.action_add_paste()
        await pilot.pause()

        assert "Primary sources:" in _text(sources, "#source-list")
        assert "Notes | included | parsed | pasted-text" in _text(sources, "#source-list")
        assert "Origin: user" in _text(sources, "#source-details")
        assert "Locator: paste://text" in _text(sources, "#source-details")
        assert "Parsed text" in _text(sources, "#source-text-preview")
        assert "First line about evidence." in _text(sources, "#source-text-preview")

        sources.action_toggle_included()
        await pilot.pause()
        assert "Notes | excluded | parsed | pasted-text" in _text(sources, "#source-list")

        sources.action_delete_selected()
        await pilot.pause()
        assert "No sources yet" in _text(sources, "#source-list")


def test_preflight_tui_surfaces_unhealthy_provider_blocker(tmp_path: Path) -> None:
    asyncio.run(_preflight_tui_unhealthy_provider(tmp_path))


async def _preflight_tui_unhealthy_provider(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Preflight")
    service.add_pasted_source(project.id, "Notes", "Grounded evidence for generation.")
    service.hosts(project.id).create_host(
        HostProfile(
            id="host-1",
            project_id=project.id,
            display_name="Host One",
            tts_provider="fake-tts",
            tts_voice="voice-a",
        ).to_record()
    )
    timestamp = format_timestamp(service.clock.now())
    episode_id = str(new_episode_id())
    service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            created_at=timestamp,
            modified_at=timestamp,
        ),
        ["host-1"],
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake", encoding="utf-8")
    config_store = UserConfigStore(tmp_path / "config.json")
    config_store.save(UserConfig(defaults={role.value: "fake:fake-v1" for role in ModelRole}))
    llm_registry = LLMProviderRegistry()
    llm_registry.register(UnhealthyLLM())
    app = DeeperDiveApp(
        service,
        provider_controller=ProviderController(
            config_store,
            llm_registry,
            {"fake-tts": FakeTTSProvider()},
        ),
        preflight_controller=PreflightController(ffmpeg_executable=ffmpeg),
    )
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.current_episode_id = episode_id
        app.action_navigate("generate")
        await pilot.pause()
        screen = _preflight(app)
        assert "Sources: 1 included / 1 indexed" in _text(screen, "#preflight-summary")
        assert "Hosts: 1" in _text(screen, "#preflight-summary")
        assert "Expected duration: 20.0 minutes" in _text(screen, "#preflight-summary")
        assert "host_generation: fake:fake-v1" in _text(screen, "#llm-preflight")
        assert "Host One: fake-tts / voice-a" in _text(screen, "#tts-preflight")
        assert "FFmpeg: available" in _text(screen, "#ffmpeg-preflight")
        assert "LLM provider 'fake' is unhealthy: offline" in _text(screen, "#preflight-issues")
        screen.action_generate()
        await pilot.pause()
        assert "Generation blocked: LLM provider 'fake' is unhealthy: offline" in _text(
            screen, "#screen-status"
        )


def test_preflight_generate_click_starts_pipeline(tmp_path: Path) -> None:
    asyncio.run(_preflight_generate_click_starts_pipeline(tmp_path))


async def _preflight_generate_click_starts_pipeline(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Generate")
    service.add_pasted_source(project.id, "Notes", "Grounded evidence for generation.")
    service.hosts(project.id).create_host(
        HostProfile(
            id="host-1",
            project_id=project.id,
            display_name="Host One",
            tts_provider="fake-tts",
            tts_voice="voice-a",
        ).to_record()
    )
    timestamp = format_timestamp(service.clock.now())
    episode_id = str(new_episode_id())
    service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            target_duration_seconds=1200,
            created_at=timestamp,
            modified_at=timestamp,
        ),
        ["host-1"],
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake", encoding="utf-8")
    config_store = UserConfigStore(tmp_path / "config.json")
    config_store.save(UserConfig(defaults={role.value: "fake:fake-v1" for role in ModelRole}))
    llm_registry = LLMProviderRegistry()
    llm_registry.register(FakeLLMProvider())
    app = DeeperDiveApp(
        service,
        provider_controller=ProviderController(
            config_store,
            llm_registry,
            {"fake-tts": FakeTTSProvider()},
        ),
        preflight_controller=PreflightController(ffmpeg_executable=ffmpeg),
    )
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.current_episode_id = episode_id
        app.action_navigate("generate")
        await pilot.pause()
        preflight = _preflight(app)
        assert "Ready to generate" in _text(preflight, "#screen-status")
        preflight.action_generate()
        await pilot.pause()
        assert isinstance(app.screen, GenerationMonitorScreen)
        monitor = app.screen
        run = service.runs(project.id).latest_for_episode(episode_id)
        assert run is not None
        assert app.current_run_id == run.id
        assert monitor._task is not None
        await asyncio.wait_for(monitor._task, timeout=5.0)


def test_preflight_tui_sanitizes_generation_start_failures(tmp_path: Path) -> None:
    asyncio.run(_preflight_tui_sanitizes_generation_start_failures(tmp_path))


async def _preflight_tui_sanitizes_generation_start_failures(tmp_path: Path) -> None:
    secret = "tui-runtime-value-654"
    key_name = "api" + "_" + "key"

    class FailingPreflightController:
        def build(self, app: object) -> PreflightPresentation:
            return PreflightPresentation(
                project_name="Project",
                source_count=1,
                indexed_source_count=1,
                host_count=1,
                target_minutes=20.0,
                llm_rows=("episode_planning: fake:fake-v1",),
                tts_rows=("Host One: fake-tts / voice-a",),
                report=PreflightReport((), PreflightEstimate(20.0, 1000, 500, None)),
            )

        def start_generation(self, app: object) -> GenerationRunRecord:
            raise RuntimeError(f"provider failed {key_name}={secret}")

    app = DeeperDiveApp(  # type: ignore[arg-type]
        _service(tmp_path),
        preflight_controller=FailingPreflightController(),
    )
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("generate")
        await pilot.pause()
        screen = _preflight(app)
        screen.action_generate()
        await pilot.pause()
        status = _text(screen, "#screen-status")
        assert secret not in status
        assert "Generation blocked: provider failed" in status
        assert f"{key_name}=[REDACTED]" in status


class UnhealthyLLM(FakeLLMProvider):
    def health(self) -> ProviderHealth:
        return ProviderHealth(False, "offline")


def _service(tmp_path: Path) -> DeeperDiveService:
    return DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)),
    )


def _home(app: DeeperDiveApp) -> HomeProjectsScreen:
    assert isinstance(app.screen, HomeProjectsScreen)
    return app.screen


def _sources(app: DeeperDiveApp) -> SourcesScreen:
    assert isinstance(app.screen, SourcesScreen)
    return app.screen


def _providers(app: DeeperDiveApp) -> ProvidersScreen:
    assert isinstance(app.screen, ProvidersScreen)
    return app.screen


def _preflight(app: DeeperDiveApp) -> PreflightScreen:
    assert isinstance(app.screen, PreflightScreen)
    return app.screen


def _set_provider_form(
    screen: ProvidersScreen,
    name: str,
    provider_type: str,
    fields: dict[str, str],
) -> None:
    screen.query_one("#provider-name", Input).value = name
    screen.query_one("#provider-type", Input).value = provider_type
    selectors = {
        "base_url": "#provider-base-url",
        "default_model": "#provider-default-model",
        "credential_env": "#provider-credential-env",
        "timeout_seconds": "#provider-timeout-seconds",
        "network_scope": "#provider-network-scope",
        "response_format": "#provider-response-format",
        "voices": "#provider-voices",
    }
    for field, selector in selectors.items():
        screen.query_one(selector, Input).value = fields.get(field, "")


def _text(
    screen: HomeProjectsScreen | SourcesScreen | ProvidersScreen | PreflightScreen,
    selector: str,
) -> str:
    return str(screen.query_one(selector, Static).render())


def _shortcut(destination: str) -> tuple[str, ...]:
    return {
        "providers": ("p",),
        "settings": ("s",),
        "help": ("?",),
        "sources": ("1",),
        "research": ("2",),
        "hosts": ("3",),
        "episode": ("4",),
        "generate": ("5",),
        "library": ("6",),
    }[destination]
