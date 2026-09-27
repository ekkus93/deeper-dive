from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from deeper_dive.conversation_generation import (
    ConversationGenerationPolicy,
    ConversationGenerationService,
)
from deeper_dive.conversation_state import ConversationStateRepository
from deeper_dive.director_decision import DirectorDecision, SegmentSignal
from deeper_dive.host_turn import HostTurnProvider
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    EpisodeRecord,
    HostEpisodeRepository,
    HostProfileRecord,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository


@dataclass
class RecordingTurnProvider(HostTurnProvider):
    calls: int = 0
    fail_on_call: int | None = None

    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("synthetic conversation provider failure")
        return {
            "speaker_id": decision.speaker_id,
            "text": f"generated turn {self.calls} with grounded deterministic context",
            "evidence_ids": list(decision.evidence_ids),
            "provider_id": "turn-provider",
            "model": "turn-model",
        }


def _database(tmp_path: Path, *, segments: int = 2) -> Database:
    database = Database(tmp_path / "project.db")
    database.initialize()
    CorpusRepository(database).create_project(ProjectRecord("p", "Project", "t", "t"))
    repository = HostEpisodeRepository(database)
    repository.create_host(HostProfileRecord("h1", "p", "Host One"))
    repository.create_host(HostProfileRecord("h2", "p", "Host Two"))
    repository.create_episode(
        EpisodeRecord(
            "e",
            "p",
            "Episode",
            "t",
            "t",
            target_duration_seconds=segments * 120,
        ),
        ["h1", "h2"],
    )
    repository.save_plan(
        EpisodePlanRecord("plan", "e", "t", "t", status="approved", plan_json="{}"),
        [
            SegmentPlanRecord(
                f"s{ordinal}",
                "plan",
                ordinal,
                f"Segment {ordinal}",
                "Advance the evidence",
                120,
                (
                    '{"title":"Segment '
                    + str(ordinal)
                    + '","purpose":"Advance the evidence",'
                    '"target_duration_seconds":120,"evidence_ids":[],"lead_host_ids":[]}'
                ),
            )
            for ordinal in range(segments)
        ],
    )
    GenerationRunRepository(database).create(
        GenerationRunRecord("r", "e", "conversation", "running", "t", "t")
    )
    return database


def test_multi_segment_generation_honors_completion_signals_atomically(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    provider = RecordingTurnProvider()

    def decide(
        segment,
        hosts: tuple[HostProfile, ...],
        state,
        remaining_seconds: int,
    ) -> DirectorDecision:
        _ = (segment, remaining_seconds)
        if state.segment_ordinal == 0 and state.segment_turn == 0:
            return DirectorDecision(
                hosts[0].id, "open", segment_signal=SegmentSignal.CONTINUE
            )
        if state.segment_ordinal == 0:
            return DirectorDecision(
                hosts[1].id,
                "finish first",
                segment_signal=SegmentSignal.COMPLETE_SEGMENT,
            )
        return DirectorDecision(
            hosts[0].id,
            "finish episode",
            segment_signal=SegmentSignal.COMPLETE_EPISODE,
        )

    service = ConversationGenerationService(database, provider, decision_provider=decide)

    turns = service.run("r", "e")

    assert [(turn.segment_ordinal, turn.turn_ordinal) for turn in turns] == [
        (0, 0),
        (0, 1),
        (1, 0),
    ]
    assert [turn.speaker_id for turn in turns] == ["h1", "h2", "h1"]
    state = ConversationStateRepository(database).get("e")
    assert state is not None
    assert state.segment_ordinal == 2
    assert state.segment_turn == 0
    assert state.participation == {"h1": 2, "h2": 1}

    repeated = service.run("r", "e")
    assert [turn.id for turn in repeated] == [turn.id for turn in turns]
    assert provider.calls == 3


def test_conversation_resume_after_failure_does_not_duplicate_prior_turn(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path, segments=1)
    failing_provider = RecordingTurnProvider(fail_on_call=2)

    def continue_then_complete(
        segment,
        hosts: tuple[HostProfile, ...],
        state,
        remaining_seconds: int,
    ) -> DirectorDecision:
        _ = (segment, remaining_seconds)
        signal = (
            SegmentSignal.CONTINUE
            if state.segment_turn == 0
            else SegmentSignal.COMPLETE_EPISODE
        )
        return DirectorDecision(hosts[0].id, "continue safely", segment_signal=signal)

    service = ConversationGenerationService(
        database,
        failing_provider,
        decision_provider=continue_then_complete,
    )

    with pytest.raises(RuntimeError, match="synthetic conversation provider failure"):
        service.run("r", "e")

    first = service.turns.list_turns("e")
    assert len(first) == 1

    resumed = ConversationGenerationService(
        database,
        RecordingTurnProvider(),
        decision_provider=continue_then_complete,
    )
    completed = resumed.run("r", "e")
    assert len(completed) == 2
    assert completed[0].id == first[0].id
    assert [turn.turn_ordinal for turn in completed] == [0, 1]


def test_non_completing_director_is_bounded_per_segment(tmp_path: Path) -> None:
    database = _database(tmp_path, segments=1)
    provider = RecordingTurnProvider()

    def never_complete(
        segment,
        hosts: tuple[HostProfile, ...],
        state,
        remaining_seconds: int,
    ) -> DirectorDecision:
        _ = (segment, state, remaining_seconds)
        return DirectorDecision(hosts[0].id, "keep going", target_words=20)

    service = ConversationGenerationService(
        database,
        provider,
        decision_provider=never_complete,
        policy=ConversationGenerationPolicy(
            max_turns_per_segment=3,
            max_turns_per_episode=6,
        ),
    )

    turns = service.run("r", "e")

    assert len(turns) == 3
    state = ConversationStateRepository(database).get("e")
    assert state is not None
    assert state.segment_ordinal == 1
    assert provider.calls == 3


def test_episode_turn_safety_bound_fails_predictably(tmp_path: Path) -> None:
    database = _database(tmp_path, segments=2)
    provider = RecordingTurnProvider()

    def never_complete(
        segment,
        hosts: tuple[HostProfile, ...],
        state,
        remaining_seconds: int,
    ) -> DirectorDecision:
        _ = (segment, state, remaining_seconds)
        return DirectorDecision(hosts[0].id, "keep going", target_words=20)

    service = ConversationGenerationService(
        database,
        provider,
        decision_provider=never_complete,
        policy=ConversationGenerationPolicy(
            max_turns_per_segment=2,
            max_turns_per_episode=2,
        ),
    )

    with pytest.raises(RuntimeError, match="maximum episode turn safety bound"):
        service.run("r", "e")
