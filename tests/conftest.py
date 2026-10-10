"""Shared pytest configuration for Deeper Dive tests."""

from __future__ import annotations

import faulthandler
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.hosts import HostProfile
from deeper_dive.model_roles import ModelRole
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore

_NO_DEFAULT_FFMPEG_NAME_PARTS = (
    "ffmpeg_unavailable",
    "ffmpeg_missing",
    "missing_ffmpeg",
)


@pytest.fixture(autouse=True)
def _default_fake_ffmpeg(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Provide deterministic FFmpeg for tests that exercise production composition.

    Tests that intentionally validate FFmpeg discovery failure opt out by name.
    """

    test_name = request.node.name.lower()
    if any(part in test_name for part in _NO_DEFAULT_FFMPEG_NAME_PARTS):
        return
    executable_dir = tmp_path / "fake-ffmpeg-bin"
    executable_dir.mkdir()
    executable = executable_dir / "ffmpeg"
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
    sys.stderr.write('missing input format')
    sys.exit(2)

if first_format == 'wav':
    try:
        with wave.open(io.BytesIO(payload), 'rb') as wav:
            source_rate = wav.getframerate()
            frame_count = wav.getnframes()
    except (EOFError, wave.Error) as exc:
        sys.stderr.write(f'invalid wav: {exc}')
        sys.exit(1)
elif first_format == 's16le':
    try:
        source_rate = int(args[args.index('-ar') + 1])
        channels = int(args[args.index('-ac') + 1])
    except (ValueError, IndexError) as exc:
        sys.stderr.write(f'invalid raw args: {exc}')
        sys.exit(2)
    frame_size = channels * 2
    if not payload or len(payload) % frame_size != 0:
        sys.stderr.write('misaligned raw input')
        sys.exit(1)
    frame_count = len(payload) // frame_size
else:
    sys.stderr.write(f'unsupported input format: {first_format}')
    sys.exit(2)

target_frames = max(1, round(frame_count * 24000 / source_rate))
sys.stdout.buffer.write(b'\x00\x00' * target_frames)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{executable_dir}{os.pathsep}{os.environ.get('PATH', '')}")


def pytest_runtest_setup(item: object) -> None:
    """Bound individual tests so a deadlock yields terminal CI evidence."""
    faulthandler.dump_traceback_later(120.0, exit=True)


def pytest_runtest_teardown(item: object, nextitem: object | None) -> None:
    """Cancel the per-test deadlock guard after normal completion."""
    faulthandler.cancel_dump_traceback_later()


@dataclass(frozen=True, slots=True)
class CompletedEpisodeAcceptance:
    """Production-created identities/artifacts, suitable for CLI and TUI assertions."""

    service: DeeperDiveService
    project_id: str
    episode_id: str
    run_id: str
    turn_ids: tuple[str, ...]
    transcript_path: Path
    audio_path: Path


@pytest.fixture
def completed_episode_acceptance(
    tmp_path: Path,
) -> Callable[[str | None], CompletedEpisodeAcceptance]:
    """Reusable deterministic LLM/TTS -> plan -> run -> review/export fixture.

    All project, source, host, episode, plan, run, turn and output records are
    created through normal production services. No repository rows are seeded.
    """
    data_dir = tmp_path / "production-acceptance"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "fake": ProviderConfig(
                    provider_type="fake", default_model="fake-v1", network_scope="local"
                ),
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    network_scope="local",
                    voices=("voice-a", "voice-b"),
                ),
            },
            defaults={
                **{role.value: "fake:fake-v1" for role in ModelRole},
                "speech_setup": "configured",
                "tts_provider": "speech",
                "tts_voice": "voice-a",
                "tts_voice_host_1": "voice-a",
                "tts_voice_host_2": "voice-b",
                "quick_deep_dive_duration_minutes": "20",
                "research_policy": "useful",
            },
        )
    )
    service = DeeperDiveService(WorkspaceManager(data_dir))
    composition = ProductionComposition.build(service=service)

    def create(project_id: str | None = None) -> CompletedEpisodeAcceptance:
        if project_id is None:
            project_id = service.create_project("Acceptance corpus").id
            service.add_pasted_source(
                project_id, "Acceptance source", "Synthetic evidence for a generated episode."
            )
            for number, voice in ((1, "voice-a"), (2, "voice-b")):
                service.hosts(project_id).create_host(
                    HostProfile(
                        f"fixture-host-{number}",
                        project_id,
                        f"Fixture Host {number}",
                        tts_provider="speech",
                        tts_voice=voice,
                    ).to_record()
                )
        episode = service.quick_deep_dive(project_id)
        composition.configured_planning_service(project_id, "fake", "fake-v1").build_plan(
            episode.id
        )
        started = GenerationStartService(composition).start(project_id, episode.id)
        composition.run_generation(project_id, started.run.id)
        finished = service.runs(project_id).get(started.run.id)
        assert finished is not None and finished.state == "completed"

        app = DeeperDiveApp(service)
        app.current_project_id = project_id
        app.current_episode_id = episode.id
        app.current_run_id = started.run.id
        turns = TranscriptReviewController().turns(app)
        assert len(turns) >= 2
        item = next(
            row for row in EpisodeLibraryController.items(app) if row.episode.id == episode.id
        )
        export = EpisodeLibraryController.export(app, item)
        assert export.audio is not None
        assert all(path.is_file() for path in export.paths)
        return CompletedEpisodeAcceptance(
            service,
            project_id,
            episode.id,
            started.run.id,
            tuple(turn.id for turn in turns),
            export.transcript,
            export.audio,
        )

    return create


@dataclass(frozen=True, slots=True)
class TwoProjectCompletedAcceptance:
    """Two isolated production-complete episodes sharing the same configured runtime."""

    first: CompletedEpisodeAcceptance
    second: CompletedEpisodeAcceptance


@pytest.fixture
def two_project_completed_acceptance(
    completed_episode_acceptance: Callable[[str | None], CompletedEpisodeAcceptance],
) -> Callable[[], TwoProjectCompletedAcceptance]:
    """Create two fully generated/exported projects through the shared acceptance path."""

    def create() -> TwoProjectCompletedAcceptance:
        first = completed_episode_acceptance(None)
        second = completed_episode_acceptance(None)
        assert first.project_id != second.project_id
        assert first.episode_id != second.episode_id
        assert first.run_id != second.run_id
        return TwoProjectCompletedAcceptance(first, second)

    return create



@dataclass(frozen=True, slots=True)
class SecondPostReviewAcceptance:
    """Reusable two-project matrix with one pending generation and byte snapshots."""

    completed: TwoProjectCompletedAcceptance
    pending_project_id: str
    pending_episode_id: str
    pending_run_id: str
    config_bytes: bytes
    pending_config_snapshot: bytes
    identity_snapshot: tuple[str, ...]


@pytest.fixture
def second_post_review_acceptance(
    two_project_completed_acceptance: Callable[[], TwoProjectCompletedAcceptance],
) -> Callable[[], SecondPostReviewAcceptance]:
    """Build the authoritative second-review acceptance matrix through production services."""

    def create() -> SecondPostReviewAcceptance:
        completed = two_project_completed_acceptance()
        service = completed.first.service
        project_id = completed.first.project_id
        composition = ProductionComposition.build(service=service)

        pending_episode = service.quick_deep_dive(project_id)
        composition.configured_planning_service(
            project_id,
            "fake",
            "fake-v1",
        ).build_plan(pending_episode.id)
        pending = GenerationStartService(composition).start(project_id, pending_episode.id)
        assert pending.run.state == "pending"

        config_path = service.workspaces.data_dir / "config.json"
        config_bytes = config_path.read_bytes()
        config = EpisodeConfigurationService(
            composition.database_for_project(project_id)
        ).load_configuration(pending_episode.id)
        snapshot_bytes = json.dumps(
            config.snapshot(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        identities = (
            completed.first.project_id,
            completed.first.episode_id,
            completed.first.run_id,
            completed.second.project_id,
            completed.second.episode_id,
            completed.second.run_id,
            pending_episode.id,
            pending.run.id,
        )
        assert len(set(identities)) == len(identities)
        return SecondPostReviewAcceptance(
            completed,
            project_id,
            pending_episode.id,
            pending.run.id,
            config_bytes,
            snapshot_bytes,
            identities,
        )

    return create
