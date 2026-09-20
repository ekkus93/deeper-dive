from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from deeper_dive.director_decision import DirectorDecision
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import HostProfile, HostRelationship
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry, TTSVoice
from deeper_dive.tts_generation import TTSArtifactRepository, TTSGenerationStage, TTSTurn


@dataclass(slots=True)
class MatrixTurnProvider:
    calls: int = 0

    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
        self.calls += 1
        return {
            "speaker_id": decision.speaker_id,
            "text": f"matrix turn {self.calls} for {decision.speaker_id}",
            "evidence_ids": list(decision.evidence_ids),
        }


def _database(tmp_path: Path, host_count: int) -> tuple[Database, tuple[str, ...]]:
    database = Database(tmp_path / f"matrix-{host_count}.db")
    database.initialize()
    CorpusRepository(database).create_project(ProjectRecord("p", "Matrix", "t", "t"))
    episodes = HostEpisodeRepository(database)
    host_ids: list[str] = []
    roles = ("Explainer", "Skeptic", "Synthesizer", "Moderator", "Practitioner")
    for index in range(host_count):
        host_id = f"h{index + 1}"
        host_ids.append(host_id)
        provider_id = "fake-tts-a" if index % 2 == 0 else "fake-tts-b"
        host = HostProfile(
            id=host_id,
            project_id="p",
            display_name=f"Host {index + 1}",
            role=roles[index % len(roles)],
            tts_provider=provider_id,
            tts_voice="voice-a",
        )
        episodes.create_host(host.to_record())
    for left, right in zip(host_ids, host_ids[1:], strict=False):
        episodes.upsert_relationship(
            HostRelationship(
                project_id="p",
                from_host_id=left,
                to_host_id=right,
                stance="handoff-peer",
                instructions="Respect the prior host's evidence before extending it.",
            ).to_record()
        )
    episodes.create_episode(EpisodeRecord("e", "p", "Matrix Episode", "t", "t"), host_ids)
    GenerationRunRepository(database).create(
        GenerationRunRecord("r", "e", "conversation", "running", "t", "t")
    )
    return database, tuple(host_ids)


@pytest.mark.parametrize("host_count", [1, 2, 3, 5])
def test_host_turn_generation_accepts_variable_host_counts(
    tmp_path: Path,
    host_count: int,
) -> None:
    database, host_ids = _database(tmp_path, host_count)
    provider = MatrixTurnProvider()
    service = HostTurnService(database, provider)

    for host_id in host_ids:
        service.generate("r", "e", DirectorDecision(host_id, f"Let {host_id} contribute."))

    turns = service.list_turns("e")
    assert [turn.speaker_id for turn in turns] == list(host_ids)
    assert [turn.turn_ordinal for turn in turns] == list(range(host_count))
    assert provider.calls == host_count

    relationships = HostEpisodeRepository(database).list_relationships("p")
    assert len(relationships) == max(0, host_count - 1)


def test_mixed_fake_tts_providers_cover_multi_host_matrix(tmp_path: Path) -> None:
    database, host_ids = _database(tmp_path, 5)
    registry = TTSProviderRegistry()
    registry.register(
        FakeTTSProvider(
            provider_id="fake-tts-a",
            voices=(TTSVoice("voice-a", "A"),),
        )
    )
    registry.register(
        FakeTTSProvider(
            provider_id="fake-tts-b",
            voices=(TTSVoice("voice-a", "B"),),
        )
    )
    repository = TTSArtifactRepository(database)
    stage = TTSGenerationStage(registry, repository, tmp_path / "tts", max_workers=1)
    turns = tuple(
        TTSTurn(
            turn_id=f"turn-{index}",
            host_id=host_id,
            text=f"speech for {host_id}",
            provider_id="fake-tts-a" if index % 2 == 0 else "fake-tts-b",
            voice="voice-a",
        )
        for index, host_id in enumerate(host_ids)
    )

    artifacts = stage.generate("r", turns)

    assert len(artifacts) == 5
    assert [artifact.provider_id for artifact in artifacts] == [
        "fake-tts-a",
        "fake-tts-b",
        "fake-tts-a",
        "fake-tts-b",
        "fake-tts-a",
    ]
    assert all(artifact.path.is_file() for artifact in artifacts)
