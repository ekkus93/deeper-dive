from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from deeper_dive.director_decision import DirectorDecision
from deeper_dive.host_turn import HostTurnService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodeRecord,
    HostEpisodeRepository,
    HostProfileRecord,
)
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord


@dataclass
class FakeTurnProvider:
    calls: int = 0
    fail_on_call: int | None = None

    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
        self.calls += 1
        if self.fail_on_call == self.calls:
            raise RuntimeError("forced provider failure")
        return {
            "speaker_id": decision.speaker_id,
            "text": f"turn {self.calls} grounded response",
            "evidence_ids": list(decision.evidence_ids),
        }


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "project.db")
    database.initialize()
    CorpusRepository(database).create_project(ProjectRecord("p", "P", "t", "t"))
    episodes = HostEpisodeRepository(database)
    episodes.create_host(HostProfileRecord("h", "p", "Host"))
    episodes.create_episode(EpisodeRecord("e", "p", "Episode", "t", "t"), ["h"])
    GenerationRunRepository(database).create(
        GenerationRunRecord("r", "e", "conversation", "running", "t", "t")
    )
    return database


def test_turn_generation_persists_citations_state_and_checkpoint(tmp_path: Path) -> None:
    database = _database(tmp_path)
    provider = FakeTurnProvider()
    service = HostTurnService(database, provider)
    decision = DirectorDecision("h", "Explain", evidence_ids=("chunk-1",), target_words=3)

    turn = service.generate("r", "e", decision)

    assert turn.speaker_id == "h"
    assert turn.evidence_ids == ("chunk-1",)
    assert service.list_turns("e") == [turn]
    state = service.states.get("e")
    assert state is not None
    assert state.segment_turn == 1
    assert state.participation == {"h": 1}
    assert state.recent_context_refs == (turn.id,)
    checkpoints = GenerationRunRepository(database).list_completed_units("r", "conversation")
    assert [item.unit_id for item in checkpoints] == ["0:0"]


def test_failure_on_turn_n_resumes_without_duplicate_prior_turns(tmp_path: Path) -> None:
    database = _database(tmp_path)
    first_provider = FakeTurnProvider(fail_on_call=2)
    service = HostTurnService(database, first_provider)
    decision = DirectorDecision("h", "Continue")

    first = service.generate("r", "e", decision)
    with pytest.raises(RuntimeError, match="forced"):
        service.generate("r", "e", decision)
    assert service.list_turns("e") == [first]
    assert service.states.get("e").segment_turn == 1  # type: ignore[union-attr]

    resumed = HostTurnService(database, FakeTurnProvider())
    second = resumed.generate("r", "e", decision)
    turns = resumed.list_turns("e")
    assert [turn.id for turn in turns] == [first.id, second.id]
    assert [turn.turn_ordinal for turn in turns] == [0, 1]


def test_turn_rejects_wrong_speaker_and_out_of_scope_citation(tmp_path: Path) -> None:
    database = _database(tmp_path)

    class BadProvider:
        def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
            return {"speaker_id": "other", "text": "bad", "evidence_ids": []}

    with pytest.raises(ValueError, match="speaker"):
        HostTurnService(database, BadProvider()).generate("r", "e", DirectorDecision("h", "x"))

    class BadCitationProvider:
        def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
            return {"speaker_id": "h", "text": "bad", "evidence_ids": ["outside"]}

    with pytest.raises(ValueError, match="outside director scope"):
        HostTurnService(database, BadCitationProvider()).generate(
            "r", "e", DirectorDecision("h", "x", evidence_ids=("allowed",))
        )
