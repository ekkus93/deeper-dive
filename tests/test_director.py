from __future__ import annotations

import pytest

from deeper_dive.conversation_state import ConversationState
from deeper_dive.director import DirectorEngine, DirectorPolicy
from deeper_dive.director_decision import SegmentSignal
from deeper_dive.episode_planner import PlannedSegment
from deeper_dive.hosts import HostProfile, HostRelationship


@pytest.mark.parametrize("host_count", [1, 2, 3, 5])
def test_director_handles_multi_host_matrix_without_ab_alternation(host_count: int) -> None:
    hosts = tuple(
        HostProfile(f"h{i}", "p1", f"Host {i}", role="analyst") for i in range(host_count)
    )
    segment = PlannedSegment(
        "Evidence",
        "analyze evidence and implications",
        180,
        evidence_ids=("c1", "c2"),
        lead_host_ids=(hosts[-1].id,),
    )
    state = ConversationState("e1", participation={host.id: i for i, host in enumerate(hosts)})
    decision = DirectorEngine().decide(segment, hosts, state, remaining_seconds=120)
    assert decision.speaker_id in {host.id for host in hosts}
    assert decision.evidence_ids == ("c1", "c2")
    assert decision.segment_signal is SegmentSignal.CONTINUE


def test_director_balances_participation_before_reusing_lead() -> None:
    hosts = (
        HostProfile("lead", "p1", "Lead", role="expert"),
        HostProfile("quiet", "p1", "Quiet", role="practitioner"),
        HostProfile("other", "p1", "Other", role="skeptic"),
    )
    segment = PlannedSegment("S", "explain findings", 120, lead_host_ids=("lead",))
    state = ConversationState("e1", participation={"lead": 4, "quiet": 0, "other": 2})
    assert DirectorEngine().decide(segment, hosts, state).speaker_id == "quiet"


def test_director_uses_relationship_context_without_forcing_disagreement() -> None:
    hosts = (
        HostProfile("h1", "p1", "One"),
        HostProfile("h2", "p1", "Two"),
    )
    relationship = HostRelationship("p1", "h1", "h2", stance="skeptical peer")
    decision = DirectorEngine().decide(
        PlannedSegment("S", "compare methods", 120),
        hosts,
        ConversationState("e1"),
        relationships=(relationship,),
    )
    assert "skeptical peer" in decision.intent
    assert "evidence-grounded" in decision.intent
    assert "do not manufacture disagreement" in decision.handoff_instruction


def test_director_stops_segment_at_hard_bound_or_exhausted_budget() -> None:
    host = HostProfile("h1", "p1", "Solo")
    segment = PlannedSegment("S", "summarize", 120)
    engine = DirectorEngine(DirectorPolicy(max_turns_per_segment=3, min_turns_per_segment=1))
    hard_stop = engine.decide(segment, (host,), ConversationState("e1", segment_turn=2))
    assert hard_stop.segment_signal is SegmentSignal.COMPLETE_SEGMENT
    exhausted = engine.decide(segment, (host,), ConversationState("e1"), remaining_seconds=10)
    assert exhausted.segment_signal is SegmentSignal.COMPLETE_SEGMENT


def test_director_rejects_empty_panel() -> None:
    with pytest.raises(ValueError, match="at least one"):
        DirectorEngine().decide(PlannedSegment("S", "purpose", 60), (), ConversationState("e1"))
