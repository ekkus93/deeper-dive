"""Deterministic end-to-end fixture generation for V1 CI qualification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeper_dive.audio_normalization import CanonicalAudio
from deeper_dive.audio_timeline import AudioTimeline, AudioTimelineRepository, TimelineItem
from deeper_dive.director_decision import DirectorDecision
from deeper_dive.export import EpisodeExporter, ManifestSource, TranscriptTurn
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import HostProfile
from deeper_dive.pipeline import DEFAULT_STAGES, PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_plan_repository import EpisodePlanRepository
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    EpisodeRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry
from deeper_dive.tts_generation import TTSArtifactRepository, TTSGenerationStage, TTSTurn

FIXTURE_PROJECT_ID = "00000000-0000-4000-8000-000000000200"
FIXTURE_EPISODE_ID = "fixture-episode"
FIXTURE_RUN_ID = "fixture-run"
FIXTURE_PLAN_ID = "fixture-plan"
FIXTURE_TIMESTAMP = "2026-09-20T00:00:00.000000Z"

PRIMARY_SOURCE_ID = "fixture-source-primary"
PRIMARY_CHUNK_ID = "fixture-chunk-primary"
SUPPLEMENTAL_SOURCE_ID = "fixture-source-supplemental"
SUPPLEMENTAL_CHUNK_ID = "fixture-chunk-supplemental"

HOSTS = (
    ("fixture-host-explainer", "Curious Explainer", "Explainer"),
    ("fixture-host-skeptic", "Skeptic", "Skeptic"),
    ("fixture-host-synthesizer", "Synthesizer", "Synthesizer"),
)

PRIMARY_TEXT = (
    "The public-domain fixture notes describe a neighborhood rain garden. "
    "Rain water is slowed by soil, native plants, and a shallow basin before it "
    "reaches the storm drain."
)
SUPPLEMENTAL_TEXT = (
    "The deterministic supplemental fixture states that permeable soil and native "
    "plant roots can reduce runoff and provide habitat."
)


@dataclass(frozen=True, slots=True)
class FixtureArtifacts:
    wav: Path
    transcript: Path
    manifest: Path
    metadata: Path


@dataclass(frozen=True, slots=True)
class FixtureResult:
    project_id: str
    episode_id: str
    run_id: str
    executed_stages: tuple[str, ...]
    skipped_stages: tuple[str, ...]
    artifacts: FixtureArtifacts


class FixtureTurnProvider:
    """Deterministic fake LLM used by the fixture conversation stage."""

    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
        evidence = ", ".join(decision.evidence_ids) or "the fixture corpus"
        return {
            "speaker_id": decision.speaker_id,
            "text": f"{decision.intent} This answer is grounded in {evidence}.",
            "evidence_ids": list(decision.evidence_ids),
        }


class DeterministicFixtureRunner:
    """Run a complete fake-provider fixture generation without network access."""

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces
        self.workspace = self.workspaces.create_project(FIXTURE_PROJECT_ID)
        self.database = Database(self.workspace.database)
        self.corpus = CorpusRepository(self.database)
        self.episodes = HostEpisodeRepository(self.database)
        self.runs = GenerationRunRepository(self.database)

    def run(self) -> FixtureResult:
        self._bootstrap()
        result = PipelineOrchestrator(
            self.runs,
            {stage: self._handler(stage) for stage in DEFAULT_STAGES},
            stages=DEFAULT_STAGES,
        ).run(FIXTURE_RUN_ID)
        return FixtureResult(
            project_id=FIXTURE_PROJECT_ID,
            episode_id=FIXTURE_EPISODE_ID,
            run_id=FIXTURE_RUN_ID,
            executed_stages=result.executed_stages,
            skipped_stages=result.skipped_stages,
            artifacts=self._artifact_paths(),
        )

    def _bootstrap(self) -> None:
        if self.corpus.get_project(FIXTURE_PROJECT_ID) is None:
            self.corpus.create_project(
                ProjectRecord(
                    id=FIXTURE_PROJECT_ID,
                    name="Deterministic Fixture Project",
                    created_at=FIXTURE_TIMESTAMP,
                    modified_at=FIXTURE_TIMESTAMP,
                    instructions="Synthetic public-domain fixture for CI qualification.",
                )
            )
        for host_id, name, role in HOSTS:
            if self.episodes.get_host(host_id) is None:
                host = HostProfile(
                    id=host_id,
                    project_id=FIXTURE_PROJECT_ID,
                    display_name=name,
                    role=role,
                    tts_provider="fake-tts",
                    tts_voice="voice-a",
                )
                self.episodes.create_host(host.to_record())
        if self.episodes.get_episode(FIXTURE_EPISODE_ID) is None:
            episode = EpisodeRecord(
                id=FIXTURE_EPISODE_ID,
                project_id=FIXTURE_PROJECT_ID,
                title="Rain Garden Fixture Deep Dive",
                focus="Explain how the fixture rain garden reduces runoff.",
                audience="general",
                technical_depth="balanced",
                target_duration_seconds=180,
                style="roundtable",
                state="draft",
                config_json=json.dumps(
                    {
                        "fixture": True,
                        "host_ids": [host[0] for host in HOSTS],
                        "research_policy": "useful",
                    },
                    sort_keys=True,
                ),
                created_at=FIXTURE_TIMESTAMP,
                modified_at=FIXTURE_TIMESTAMP,
            )
            self.episodes.create_episode(episode, [host[0] for host in HOSTS])
        if self.runs.get(FIXTURE_RUN_ID) is None:
            self.runs.create(
                GenerationRunRecord(
                    id=FIXTURE_RUN_ID,
                    episode_id=FIXTURE_EPISODE_ID,
                    stage="sources",
                    state="pending",
                    created_at=FIXTURE_TIMESTAMP,
                    modified_at=FIXTURE_TIMESTAMP,
                )
            )

    def _handler(self, stage: str) -> Callable[[PipelineContext], None]:
        return {
            "sources": self._stage_sources,
            "research": self._stage_research,
            "planning": self._stage_planning,
            "conversation": self._stage_conversation,
            "verification": self._stage_verification,
            "tts": self._stage_tts,
            "composition": self._stage_composition,
            "export": self._stage_export,
        }[stage]

    def _stage_sources(self, context: PipelineContext) -> None:
        self._create_source_once(
            source_id=PRIMARY_SOURCE_ID,
            chunk_id=PRIMARY_CHUNK_ID,
            origin="user",
            title="Public-domain rain garden notes",
            locator="fixture://primary/rain-garden-notes",
            text=PRIMARY_TEXT,
        )

    def _stage_research(self, context: PipelineContext) -> None:
        self._create_source_once(
            source_id=SUPPLEMENTAL_SOURCE_ID,
            chunk_id=SUPPLEMENTAL_CHUNK_ID,
            origin="supplemental",
            title="Deterministic supplemental runoff note",
            locator="fixture://supplemental/runoff-note",
            text=SUPPLEMENTAL_TEXT,
        )

    def _stage_planning(self, context: PipelineContext) -> None:
        plan = EpisodePlanRecord(
            id=FIXTURE_PLAN_ID,
            episode_id=FIXTURE_EPISODE_ID,
            status="approved",
            plan_json=json.dumps({"target_duration_seconds": 180}, sort_keys=True),
            created_at=FIXTURE_TIMESTAMP,
            modified_at=FIXTURE_TIMESTAMP,
        )
        segments = [
            SegmentPlanRecord(
                id="fixture-segment-0",
                episode_plan_id=FIXTURE_PLAN_ID,
                ordinal=0,
                title="What the fixture corpus says",
                purpose="Ground the conversation in primary and supplemental evidence.",
                target_duration_seconds=180,
                segment_json=json.dumps(
                    {
                        "evidence_ids": [PRIMARY_CHUNK_ID, SUPPLEMENTAL_CHUNK_ID],
                        "lead_host_ids": [HOSTS[0][0], HOSTS[1][0], HOSTS[2][0]],
                        "questions": ["How does the rain garden reduce runoff?"],
                    },
                    sort_keys=True,
                ),
            )
        ]
        EpisodePlanRepository(self.database).replace(plan, segments)

    def _stage_conversation(self, context: PipelineContext) -> None:
        service = HostTurnService(self.database, FixtureTurnProvider())
        decisions = (
            DirectorDecision(
                HOSTS[0][0],
                "Introduce the rain garden mechanism.",
                evidence_ids=(PRIMARY_CHUNK_ID,),
                target_words=24,
            ),
            DirectorDecision(
                HOSTS[1][0],
                "Probe what the supplemental evidence adds.",
                evidence_ids=(SUPPLEMENTAL_CHUNK_ID,),
                target_words=24,
            ),
            DirectorDecision(
                HOSTS[2][0],
                "Synthesize the primary and supplemental evidence.",
                evidence_ids=(PRIMARY_CHUNK_ID, SUPPLEMENTAL_CHUNK_ID),
                target_words=28,
            ),
        )
        existing = service.list_turns(FIXTURE_EPISODE_ID)
        for decision in decisions[len(existing) :]:
            service.generate(context.run_id, context.episode_id, decision)

    def _stage_verification(self, context: PipelineContext) -> None:
        with self.database.connection() as db:
            row = db.execute(
                "SELECT COUNT(*) FROM conversation_turns WHERE episode_id=?",
                (FIXTURE_EPISODE_ID,),
            ).fetchone()
        turn_count = 0 if row is None else int(row[0])
        if turn_count != 3:
            raise RuntimeError(f"fixture conversation expected 3 turns, found {turn_count}")

    def _stage_tts(self, context: PipelineContext) -> None:
        registry = TTSProviderRegistry()
        registry.register(FakeTTSProvider())
        turns = tuple(
            TTSTurn(
                turn_id=row["id"],
                host_id=row["speaker_id"],
                text=row["text"],
                provider_id="fake-tts",
                voice="voice-a",
            )
            for row in self._conversation_rows()
        )
        TTSGenerationStage(
            registry,
            TTSArtifactRepository(self.database),
            self.workspace.cache / "tts",
            max_workers=1,
        ).generate(context.run_id, turns)

    def _stage_composition(self, context: PipelineContext) -> None:
        artifacts = self._tts_artifacts_by_turn()
        items = tuple(
            TimelineItem.clip(
                turn_id=row["id"],
                host_id=row["speaker_id"],
                artifact_id=artifacts[row["id"]],
                duration_seconds=0.25,
                metadata={"chapter_title": f"{row['display_name']} turn"},
            )
            for row in self._conversation_rows()
        )
        AudioTimelineRepository(self.database).save(AudioTimeline.build(FIXTURE_EPISODE_ID, items))

    def _stage_export(self, context: PipelineContext) -> None:
        artifacts = self._artifact_paths()
        exporter = EpisodeExporter(self.workspace.output)
        turns = tuple(
            TranscriptTurn(str(row["display_name"]), str(row["text"]))
            for row in self._conversation_rows()
        )
        sources = tuple(
            ManifestSource(str(row["title"]), str(row["origin"]), str(row["locator"]))
            for row in self._source_rows()
        )
        exporter.write_transcript(artifacts.transcript, "Rain Garden Fixture Deep Dive", turns)
        exporter.write_manifest(artifacts.manifest, sources)
        exporter.write_metadata(
            artifacts.metadata,
            {
                "project_id": FIXTURE_PROJECT_ID,
                "episode_id": FIXTURE_EPISODE_ID,
                "run_id": FIXTURE_RUN_ID,
                "network_required": False,
                "provider_mode": "fake",
                "source_count": len(sources),
                "turn_count": len(turns),
            },
        )
        exporter.write_wav(
            artifacts.wav,
            CanonicalAudio(
                pcm=b"\x00\x00" * 720,
                sample_rate_hz=24_000,
                channels=1,
                sample_width_bytes=2,
                duration_seconds=0.03,
                source_format="pcm_s16le",
                source_media_type="audio/wav",
            ),
        )

    def _create_source_once(
        self,
        *,
        source_id: str,
        chunk_id: str,
        origin: str,
        title: str,
        locator: str,
        text: str,
    ) -> None:
        if self.corpus.get_source(source_id) is not None:
            return
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.corpus.create_source(
            SourceRecord(
                id=source_id,
                project_id=FIXTURE_PROJECT_ID,
                origin=origin,
                source_type="fixture-text",
                title=title,
                locator=locator,
                content_hash=digest,
                included=True,
                status="parsed",
                imported_at=FIXTURE_TIMESTAMP,
            )
        )
        self.corpus.create_chunk(
            SourceChunkRecord(
                id=chunk_id,
                source_id=source_id,
                ordinal=0,
                text=text,
                content_hash=digest,
                location=f"{locator}#chunk-0",
            )
        )

    def _conversation_rows(self) -> tuple[dict[str, Any], ...]:
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT ct.id, ct.speaker_id, ct.text, h.display_name
                FROM conversation_turns ct
                JOIN hosts h ON h.id = ct.speaker_id
                WHERE ct.episode_id=?
                ORDER BY ct.segment_ordinal, ct.turn_ordinal""",
                (FIXTURE_EPISODE_ID,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def _source_rows(self) -> tuple[dict[str, Any], ...]:
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT title, origin, locator FROM sources
                WHERE project_id=? ORDER BY origin DESC, title""",
                (FIXTURE_PROJECT_ID,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def _tts_artifacts_by_turn(self) -> dict[str, str]:
        with self.database.connection() as db:
            rows = db.execute("SELECT turn_id, artifact_id FROM tts_artifacts").fetchall()
        return {str(row["turn_id"]): str(row["artifact_id"]) for row in rows}

    def _artifact_paths(self) -> FixtureArtifacts:
        root = self.workspace.output / "deterministic-fixture"
        return FixtureArtifacts(
            wav=root.with_suffix(".wav"),
            transcript=root.with_suffix(".md"),
            manifest=root.with_name(root.name + "-sources.json"),
            metadata=root.with_name(root.name + "-metadata.json"),
        )
