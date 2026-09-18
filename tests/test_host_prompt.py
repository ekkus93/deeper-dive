from __future__ import annotations

import pytest

from deeper_dive.conversation_state import ConversationState
from deeper_dive.director_decision import DirectorDecision
from deeper_dive.host_prompt import HostPromptAssembler, PromptEvidence, RecentDialogueTurn
from deeper_dive.hosts import HostProfile, HostRelationship


def test_host_prompt_assembles_profile_director_state_dialogue_and_provenance() -> None:
    host = HostProfile(
        "host-a",
        "project-1",
        "Ada",
        role="skeptic",
        expertise="methods",
        instructions="Probe uncertainty.",
        behavior={"skepticism": 0.8},
        evidence_priorities=["primary sources"],
    )
    decision = DirectorDecision(
        "host-a",
        "Explain the strongest evidence and its limitation.",
        evidence_ids=("chunk-2",),
        target_duration_seconds=30,
        target_words=75,
        handoff_instruction="Invite the explainer to respond.",
    )
    state = ConversationState(
        "episode-1",
        segment_ordinal=2,
        segment_turn=4,
        running_summary="The panel established the baseline.",
        unresolved_topics=("causality",),
        recent_context_refs=("turn-3", "turn-4"),
        participation={"host-a": 2, "host-b": 2},
    )
    evidence = (
        PromptEvidence("chunk-1", "source-1", "Irrelevant text", "user", "p. 1"),
        PromptEvidence("chunk-2", "source-2", "Relevant result", "supplemental", "§ Results"),
    )
    relationships = (
        HostRelationship("project-1", "host-a", "host-b", "skeptical peer", "Challenge gently", 0.7),
        HostRelationship("project-1", "host-b", "host-a", "explainer", "Clarify", 0.8),
    )

    prompt = HostPromptAssembler().assemble(
        host=host,
        decision=decision,
        recent_dialogue=(RecentDialogueTurn("host-b", "What does the study show?"),),
        state=state,
        evidence=evidence,
        relationships=relationships,
        citation_behavior="cite every material factual claim",
    )

    assert "Ada" in prompt.system
    assert "Probe uncertainty" in prompt.system
    assert decision.intent in prompt.system
    assert "Never invent evidence IDs" in prompt.system
    assert prompt.context["recent_dialogue"] == [
        {"speaker_id": "host-b", "text": "What does the study show?"}
    ]
    conversation = prompt.context["conversation_state"]
    assert isinstance(conversation, dict)
    assert conversation["running_summary"] == "The panel established the baseline."
    assert conversation["unresolved_topics"] == ["causality"]
    assert prompt.context["evidence"] == [
        {
            "id": "chunk-2",
            "source_id": "source-2",
            "origin": "supplemental",
            "location": "§ Results",
            "text": "Relevant result",
        }
    ]
    assert prompt.context["relationships"] == [
        "Relationship to host-b: skeptical peer; affinity=0.70; Challenge gently"
    ]
    assert "chunk-1" not in HostPromptAssembler.as_json(prompt)


def test_host_prompt_rejects_wrong_speaker_or_missing_directed_evidence() -> None:
    host = HostProfile("host-a", "project-1", "Ada")
    state = ConversationState("episode-1")
    assembler = HostPromptAssembler()

    with pytest.raises(ValueError, match="speaker"):
        assembler.assemble(
            host=host,
            decision=DirectorDecision("host-b", "Respond"),
            recent_dialogue=(),
            state=state,
            evidence=(),
        )

    with pytest.raises(ValueError, match="missing directed evidence"):
        assembler.assemble(
            host=host,
            decision=DirectorDecision("host-a", "Respond", evidence_ids=("missing",)),
            recent_dialogue=(),
            state=state,
            evidence=(),
        )
