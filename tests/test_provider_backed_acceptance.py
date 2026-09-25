from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from textual.widgets import Static

from deeper_dive import cli as cli_module
from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeExportResult, EpisodeLibraryExportService
from deeper_dive.episode_library_screen import EpisodeLibraryScreen
from deeper_dive.generation_monitor import GenerationMonitorScreen
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight import PreflightBlockedError
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.transcript_review_screen import TranscriptReviewScreen
from deeper_dive.tts_generation import TTS_ARTIFACT_STATUS_COMPLETE
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore

_PROVIDER_MARKER = "Configured fake provider host turn marker"
_DIRECTOR_MARKER = "Configured fake directing decision marker"


@dataclass(slots=True)
class ProviderAcceptanceFixture:
    composition: ProductionComposition
    project_id: str
    episode_id: str
    episode: EpisodeRecord
    data_dir: Path


@dataclass(slots=True)
class AcceptanceRunResult:
    run: GenerationRunRecord
    export: EpisodeExportResult


def test_production_composition_provider_backed_generation_and_export(
    tmp_path: Path,
) -> None:
    fixture = _acceptance_fixture(tmp_path)

    result = _run_and_export(fixture, tmp_path / "ffmpeg")

    _assert_provider_backed_outputs(fixture, result)


def test_generation_start_blocks_missing_providers_before_output(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(defaults={role.value: "ghost:fake-v1" for role in ModelRole})
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Missing providers")
    composition.service.add_pasted_source(
        project.id,
        "Source",
        "Provider readiness should fail before output is produced.",
    )
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Missing providers episode",
            focus="Fail before output",
            target_duration_seconds=60,
            host_ids=(host.id,),
        ),
    )

    with pytest.raises(PreflightBlockedError, match="generation blocked by preflight"):
        GenerationStartService(composition, ffmpeg_executable=_fake_ffmpeg(tmp_path)).start(
            project.id,
            episode.id,
        )

    project_root = composition.service.workspaces.project_root(project.id)
    assert composition.generation_run_repository(project.id).latest_for_episode(episode.id) is None
    assert not (project_root / "output").exists()
    assert not (project_root / "exports").exists()


def test_cli_provider_backed_acceptance_workflow(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    _write_provider_config(data_dir)
    _patch_ffmpeg(monkeypatch)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "source.md").write_text(
        "# CLI corpus\n\nA deterministic provider-backed source.\n",
        encoding="utf-8",
    )
    base = ["--data-dir", str(data_dir), "--json"]

    project = _json_call([*base, "project", "create", "CLI acceptance"], capsys)
    project_id = str(project["id"])
    sources = _json_call([*base, "source", "add", project_id, str(corpus)], capsys)
    host = _json_call([*base, "host", "create", project_id, "curious_explainer"], capsys)
    host_id = str(host["id"])
    _json_call(
        [
            *base,
            "host",
            "voice",
            project_id,
            host_id,
            "--provider",
            "speech",
            "--voice",
            "voice-a",
        ],
        capsys,
    )
    episode = _json_call(
        [
            *base,
            "episode",
            "create",
            project_id,
            "--title",
            "CLI provider acceptance",
            "--focus",
            "Assert provider-backed generation",
            "--duration",
            "60",
            "--hosts",
            host_id,
            "--research-policy",
            "off",
        ],
        capsys,
    )
    episode_id = _episode_id(episode)
    plan = _json_call([*base, "episode", "plan", project_id, episode_id], capsys)
    run = _json_call([*base, "episode", "generate", project_id, episode_id], capsys)
    status = _json_call([*base, "episode", "status", project_id, episode_id], capsys)
    export = _json_call(
        [
            *base,
            "episode",
            "export",
            project_id,
            episode_id,
            "--output-dir",
            str(tmp_path / "cli-exports"),
        ],
        capsys,
    )

    assert sources["imported"]
    assert plan["segments"]
    assert run["state"] == "completed"
    assert run["stage"] == "export"
    assert status["run"]["id"] == run["id"]
    assert export["episode_id"] == episode_id
    _assert_export_paths(export)
    transcript = Path(str(export["transcript"])).read_text(encoding="utf-8")
    assert _PROVIDER_MARKER in transcript
    assert _DIRECTOR_MARKER in transcript

    db_path = data_dir / "projects" / project_id / "project.db"
    _assert_sqlite_provider_artifacts(db_path)


def test_cli_duplicate_start_and_pause_resume_acceptance_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _acceptance_fixture(tmp_path)
    _hold_generation(monkeypatch)
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: fixture.composition),
    )
    _patch_ffmpeg(monkeypatch)
    base = ["--data-dir", str(fixture.data_dir), "--json", "episode"]

    first = _json_call([*base, "generate", fixture.project_id, fixture.episode_id], capsys)
    duplicate = _json_call([*base, "generate", fixture.project_id, fixture.episode_id], capsys)
    paused = _json_call([*base, "pause", fixture.project_id, fixture.episode_id], capsys)
    resumed = _json_call([*base, "resume", fixture.project_id, fixture.episode_id], capsys)

    assert duplicate["id"] == first["id"]
    assert paused["id"] == first["id"]
    assert paused["state"] == "paused"
    assert resumed["id"] == first["id"]
    assert resumed["state"] == "pending"


def test_tui_provider_backed_acceptance_workflow(tmp_path: Path) -> None:
    asyncio.run(_tui_provider_backed_acceptance_workflow(tmp_path))


async def _tui_provider_backed_acceptance_workflow(tmp_path: Path) -> None:
    fixture = _acceptance_fixture(tmp_path)
    controller = PreflightController(ffmpeg_executable=_fake_ffmpeg(tmp_path))
    app = DeeperDiveApp(
        fixture.composition.service,
        provider_controller=fixture.composition.provider_controller,
        preflight_controller=controller,
        generation_monitor_controller=fixture.composition.generation_monitor_controller,
    )
    async with app.run_test(size=(120, 40)) as pilot:
        app.current_project_id = fixture.project_id
        app.current_project_name = "Provider acceptance"
        app.current_episode_id = fixture.episode_id
        app.action_navigate("generate")
        await pilot.pause()
        preflight = _preflight_screen(app)
        first = controller.start_generation(app)
        second = controller.start_generation(app)
        assert second.id == first.id

        preflight.action_generate()
        await pilot.pause()
        assert isinstance(app.screen, GenerationMonitorScreen)
        monitor = app.screen
        assert app.current_run_id == first.id
        assert monitor._task is not None
        await asyncio.wait_for(monitor._task, timeout=5.0)

        app.action_navigate("library")
        await pilot.pause()
        library = _library_screen(app)
        assert "completed" in _text(library, "#episode-library-list")
        library.action_export_selected()
        await pilot.pause()
        assert "Exported:" in _text(library, "#screen-status")
        library.action_open_selected()
        await pilot.pause()
        assert isinstance(app.screen, TranscriptReviewScreen)

    run = fixture.composition.generation_run_repository(fixture.project_id).latest_for_episode(
        fixture.episode_id
    )
    assert run is not None
    episode = fixture.composition.service.hosts(fixture.project_id).get_episode(fixture.episode_id)
    assert episode is not None
    export = EpisodeLibraryExportService(fixture.composition.service.workspaces).export(
        fixture.project_id,
        episode,
        run,
        output_dir=tmp_path / "tui-exports",
    )
    _assert_provider_backed_outputs(fixture, AcceptanceRunResult(run, export))


def _acceptance_fixture(tmp_path: Path) -> ProviderAcceptanceFixture:
    data_dir = tmp_path / "data"
    _write_provider_config(data_dir)
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Provider acceptance")
    composition.service.add_pasted_source(
        project.id,
        "Fixture source",
        "Deterministic source text for provider-backed acceptance.",
    )
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Provider acceptance episode",
            focus="Prove provider-backed generation and export",
            target_duration_seconds=60,
            host_ids=(host.id,),
            research_overrides={"policy": "off"},
        ),
    )
    composition.configured_planning_service(project.id, "planner", "fake-v1").build_plan(
        episode.id
    )
    return ProviderAcceptanceFixture(composition, project.id, episode.id, episode, data_dir)


def _write_provider_config(data_dir: Path) -> None:
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={role.value: "planner:fake-v1" for role in ModelRole},
        )
    )


def _run_and_export(
    fixture: ProviderAcceptanceFixture,
    ffmpeg: Path,
) -> AcceptanceRunResult:
    run = GenerationStartService(fixture.composition, ffmpeg_executable=ffmpeg).start(
        fixture.project_id,
        fixture.episode_id,
    )
    completed = fixture.composition.run_generation(fixture.project_id, run.id).run
    export = EpisodeLibraryExportService(fixture.composition.service.workspaces).export(
        fixture.project_id,
        fixture.episode,
        completed,
        output_dir=ffmpeg.parent / "exports",
    )
    return AcceptanceRunResult(completed, export)


def _assert_provider_backed_outputs(
    fixture: ProviderAcceptanceFixture,
    result: AcceptanceRunResult,
) -> None:
    assert result.run.state == "completed"
    assert result.run.stage == "export"
    _assert_export_result(result.export, result.run.id, fixture.episode_id, fixture.project_id)
    database = fixture.composition.database_for_project(fixture.project_id)
    turns = HostTurnService(database).list_turns(fixture.episode_id)
    assert turns
    assert any(_PROVIDER_MARKER in turn.text for turn in turns)
    assert any(_DIRECTOR_MARKER in turn.text for turn in turns)
    turn_service = HostTurnService(database)
    for turn in turns:
        identity = turn_service.provider_identity(turn.id)
        assert identity is not None
        assert identity.provider_id == "planner"
        assert identity.model == "fake-v1"
    _assert_sqlite_provider_artifacts(database.path)


def _assert_export_result(
    export: EpisodeExportResult,
    run_id: str,
    episode_id: str,
    project_id: str,
) -> None:
    assert export.transcript.is_file()
    assert export.manifest.is_file()
    assert export.metadata.is_file()
    assert export.audio is not None
    assert export.audio.is_file()
    transcript = export.transcript.read_text(encoding="utf-8")
    metadata = json.loads(export.metadata.read_text(encoding="utf-8"))
    assert _PROVIDER_MARKER in transcript
    assert _DIRECTOR_MARKER in transcript
    assert metadata["run_id"] == run_id
    assert metadata["episode_id"] == episode_id
    assert metadata["project_id"] == project_id
    assert b"FAKE-WAV" in export.audio.read_bytes()


def _assert_export_paths(export: dict[str, object]) -> None:
    for key in ("transcript", "manifest", "metadata", "audio"):
        value = export[key]
        assert isinstance(value, str)
        assert Path(value).is_file()
    assert set(export["paths"]) == {
        export["transcript"],
        export["manifest"],
        export["metadata"],
        export["audio"],
    }


def _assert_sqlite_provider_artifacts(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        turns = connection.execute("SELECT id,text FROM conversation_turns").fetchall()
        artifacts = connection.execute("SELECT * FROM tts_artifacts").fetchall()
    assert turns
    assert any(_PROVIDER_MARKER in str(row["text"]) for row in turns)
    assert artifacts
    for artifact in artifacts:
        assert str(artifact["status"]) == TTS_ARTIFACT_STATUS_COMPLETE
        assert str(artifact["provider_id"]) == "speech"
        assert str(artifact["voice"]) == "voice-a"
        assert Path(str(artifact["path"])).is_file()


def _json_call(args: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def _episode_id(payload: dict[str, Any]) -> str:
    nested = payload.get("episode")
    if isinstance(nested, dict):
        return str(nested["id"])
    return str(payload["id"])


def _fake_ffmpeg(tmp_path: Path) -> Path:
    executable = tmp_path / "ffmpeg"
    executable.write_text("fake", encoding="utf-8")
    return executable


def _patch_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeper_dive.preflight.FFmpegConfig.detect",
        staticmethod(lambda executable=None: executable or Path("/fake/ffmpeg")),
    )


def _hold_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    def run_generation(
        self: ProductionComposition,
        project_id: str,
        run_id: str,
        *,
        progress: object | None = None,
    ) -> object:
        _ = progress
        repository = self.generation_run_repository(project_id)
        run = repository.get(run_id)
        assert run is not None
        return type("PipelineResult", (), {"run": run, "completed": (), "failed": ()})()

    monkeypatch.setattr(ProductionComposition, "run_generation", run_generation)


def _preflight_screen(app: DeeperDiveApp) -> PreflightScreen:
    assert isinstance(app.screen, PreflightScreen)
    return app.screen


def _library_screen(app: DeeperDiveApp) -> EpisodeLibraryScreen:
    assert isinstance(app.screen, EpisodeLibraryScreen)
    return app.screen


def _text(screen: EpisodeLibraryScreen, selector: str) -> str:
    return str(screen.query_one(selector, Static).render())
