from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from deeper_dive import model_roles
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import (
    EpisodeExportResult,
    EpisodeLibraryExportService,
)
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import (
    CorpusRepository,
    SourceChunkRecord,
    SourceRecord,
)
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


def create_ready_followup_fixture(tmp_path: Path) -> ReadyFollowupFixture:
    """Create the shared deterministic follow-up production workflow fixture."""

    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "dialogue": ProviderConfig(
                    provider_type="fake",
                    default_model="fake-v1",
                ),
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
    episode = _create_episode(
        database,
        project.id,
        host.id,
        title="R6 acceptance episode",
        focus="deterministic production acceptance marker",
    )
    _save_plan(
        database,
        episode.id,
        plan_id="plan-r6",
        segment_id="segment-r6",
        chunk_id="chunk-r6",
        purpose="Exercise the full configured fake-provider workflow.",
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake ffmpeg", encoding="utf-8")
    return ReadyFollowupFixture(
        data_dir=data_dir,
        ffmpeg=ffmpeg,
        composition=composition,
        project_id=project.id,
        episode_id=episode.id,
        host_id=host.id,
    )


def create_additional_followup_episode(
    ready: ReadyFollowupFixture,
    *,
    suffix: str,
    chunk_id: str,
    source_text: str,
) -> str:
    """Add another planned episode to the same fixture project."""

    _create_indexed_source(
        ready.database,
        ready.project_id,
        source_id=f"source-{suffix}",
        chunk_id=chunk_id,
        text=source_text,
    )
    episode = _create_episode(
        ready.database,
        ready.project_id,
        ready.host_id,
        title=f"R6 acceptance episode {suffix}",
        focus=f"deterministic production acceptance marker {suffix}",
    )
    _save_plan(
        ready.database,
        episode.id,
        plan_id=f"plan-{suffix}",
        segment_id=f"segment-{suffix}",
        chunk_id=chunk_id,
        purpose=f"Exercise isolated follow-up fixture workflow {suffix}.",
    )
    return episode.id


def run_followup_fixture(ready: ReadyFollowupFixture) -> CompletedFollowupFixture:
    return run_followup_episode(ready, ready.episode_id)


def run_followup_episode(
    ready: ReadyFollowupFixture,
    episode_id: str,
) -> CompletedFollowupFixture:
    run = ready.composition.create_generation_run(ready.project_id, episode_id)
    completed = ready.composition.run_generation(ready.project_id, run.id).run
    episode = HostEpisodeRepository(ready.database).get_episode(episode_id)
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
        episode_id=episode_id,
        host_id=ready.host_id,
        chunk_id=ready.chunk_id if episode_id == ready.episode_id else "",
        run=completed,
        export=exported,
    )


def _create_episode(
    database: Database,
    project_id: str,
    host_id: str,
    *,
    title: str,
    focus: str,
):
    return EpisodeConfigurationService(database).create(
        project_id,
        EpisodeConfiguration(
            title=title,
            focus=focus,
            target_duration_seconds=60,
            host_ids=(host_id,),
            research_overrides={"policy": "off"},
        ),
    )


def _save_plan(
    database: Database,
    episode_id: str,
    *,
    plan_id: str,
    segment_id: str,
    chunk_id: str,
    purpose: str,
) -> None:
    plan_json = json.dumps({"target_duration_seconds": 60})
    segment_json = json.dumps(
        {
            "title": "Acceptance segment",
            "purpose": purpose,
            "target_duration_seconds": 60,
            "questions": ["What marker proves production routing?"],
            "evidence_ids": [chunk_id],
            "lead_host_ids": [],
        }
    )
    HostEpisodeRepository(database).save_plan(
        EpisodePlanRecord(
            id=plan_id,
            episode_id=episode_id,
            status="approved",
            plan_json=plan_json,
            created_at="2026-09-27T00:00:00Z",
            modified_at="2026-09-27T00:00:00Z",
        ),
        [
            SegmentPlanRecord(
                id=segment_id,
                episode_plan_id=plan_id,
                ordinal=0,
                title="Acceptance segment",
                purpose=purpose,
                target_duration_seconds=60,
                segment_json=segment_json,
            )
        ],
    )


def _create_indexed_source(
    database: Database,
    project_id: str,
    *,
    source_id: str = "source-r6",
    chunk_id: str = "chunk-r6",
    text: str = (
        "R6 acceptance source marker with evidence, voice, format, artifact, and "
        "export identity."
    ),
) -> None:
    corpus = CorpusRepository(database)
    corpus.create_source(
        SourceRecord(
            id=source_id,
            project_id=project_id,
            origin="user",
            source_type="text/plain",
            title=f"R6 deterministic source {source_id}",
            imported_at="2026-09-27T00:00:00Z",
            status="indexed",
        )
    )
    corpus.create_chunk(
        SourceChunkRecord(
            id=chunk_id,
            source_id=source_id,
            ordinal=0,
            text=text,
            content_hash=f"hash-{chunk_id}",
            location="line 1",
        )
    )
