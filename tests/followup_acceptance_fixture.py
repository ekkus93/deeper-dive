from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeper_dive import model_roles
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeExportResult, EpisodeLibraryExportService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.repositories import CorpusRepository, SourceChunkRecord, SourceRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


@dataclass(frozen=True, slots=True)
class ReadyFollowupFixture:
    data_dir: Path
    ffmpeg: Path
    composition: ProductionComposition
    project_id: str
    episode_id: str
    host_id: str
    chunk_id: str = "chunk-r6"

    @property
    def database(self) -> Database:
        return self.composition.database_for_project(self.project_id)


@dataclass(frozen=True, slots=True)
class CompletedFollowupFixture(ReadyFollowupFixture):
    run: GenerationRunRecord | None = None
    export: EpisodeExportResult | None = None


class _AcceptancePlanGenerator:
    def generate_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        evidence_ids = {
            str(item.get("chunk_id", ""))
            for item in request.get("evidence", [])
            if isinstance(item, dict)
        }
        if "chunk-r6" not in evidence_ids:
            raise AssertionError("acceptance fixture did not retrieve chunk-r6 evidence")
        return {
            "segments": [
                {
                    "title": "Acceptance segment",
                    "purpose": "Exercise the full configured fake-provider workflow.",
                    "target_duration_seconds": 60,
                    "questions": ["What marker proves production routing?"],
                    "evidence_ids": ["chunk-r6"],
                    "lead_host_ids": [],
                }
            ]
        }


def create_ready_followup_fixture(tmp_path: Path) -> ReadyFollowupFixture:
    """Create the shared deterministic follow-up production workflow fixture."""

    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "dialogue": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(
                    provider_type="fake-tts",
                    voices=("voice-a",),
                    response_format="wav",
                ),
            },
            defaults={role.value: "dialogue:fake-v1" for role in model_roles.ModelRole},
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("R6 shared acceptance")
    database = composition.database_for_project(project.id)
    _create_indexed_source(database, project.id)
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(database).create(
        project.id,
        EpisodeConfiguration(
            title="R6 acceptance episode",
            focus="deterministic production acceptance marker",
            target_duration_seconds=60,
            host_ids=(host.id,),
            research_overrides={"policy": "off"},
        ),
    )
    planner = composition.planning_service(project.id, _AcceptancePlanGenerator())
    planner.build_plan(episode.id)
    planner.approve_plan(episode.id)
    ffmpeg = tmp_path / "ffmpeg"
    _write_fake_ffmpeg(ffmpeg)
    return ReadyFollowupFixture(
        data_dir=data_dir,
        ffmpeg=ffmpeg,
        composition=composition,
        project_id=project.id,
        episode_id=episode.id,
        host_id=host.id,
    )


def run_followup_fixture(ready: ReadyFollowupFixture) -> CompletedFollowupFixture:
    run = ready.composition.create_generation_run(ready.project_id, ready.episode_id)
    completed = ready.composition.run_generation(ready.project_id, run.id).run
    episode = HostEpisodeRepository(ready.database).get_episode(ready.episode_id)
    assert episode is not None
    exported = EpisodeLibraryExportService(ready.composition.service.workspaces).export(
        ready.project_id,
        episode,
        completed,
    )
    return CompletedFollowupFixture(
        data_dir=ready.data_dir,
        ffmpeg=ready.ffmpeg,
        composition=ready.composition,
        project_id=ready.project_id,
        episode_id=ready.episode_id,
        host_id=ready.host_id,
        chunk_id=ready.chunk_id,
        run=completed,
        export=exported,
    )


def _create_indexed_source(database: Database, project_id: str) -> None:
    corpus = CorpusRepository(database)
    corpus.create_source(
        SourceRecord(
            id="source-r6",
            project_id=project_id,
            origin="user",
            source_type="text/plain",
            title="R6 deterministic source",
            imported_at="2026-09-27T00:00:00Z",
            status="indexed",
        )
    )
    corpus.create_chunk(
        SourceChunkRecord(
            id="chunk-r6",
            source_id="source-r6",
            ordinal=0,
            text=(
                "R6 acceptance source marker with evidence, voice, format, artifact, and "
                "export identity."
            ),
            content_hash="hash-r6",
            location="line 1",
        )
    )


def _write_fake_ffmpeg(executable: Path) -> None:
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
