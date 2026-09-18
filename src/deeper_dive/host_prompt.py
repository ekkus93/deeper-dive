"""Grounded prompt/context assembly for one directed host turn."""

from __future__ import annotations

import json
from dataclasses import dataclass

from deeper_dive.conversation_state import ConversationState
from deeper_dive.director_decision import DirectorDecision
from deeper_dive.hosts import HostProfile, HostRelationship


@dataclass(frozen=True, slots=True)
class PromptEvidence:
    """Evidence exposed to a host with stable provenance metadata."""

    id: str
    source_id: str
    text: str
    origin: str
    location: str | None = None


@dataclass(frozen=True, slots=True)
class RecentDialogueTurn:
    speaker_id: str
    text: str


@dataclass(frozen=True, slots=True)
class HostPromptContext:
    """Structured prompt input suitable for provider adapters."""

    system: str
    context: dict[str, object]


class HostPromptAssembler:
    """Assemble only the bounded state and evidence authorized for the next turn."""

    def assemble(
        self,
        *,
        host: HostProfile,
        decision: DirectorDecision,
        recent_dialogue: tuple[RecentDialogueTurn, ...],
        state: ConversationState,
        evidence: tuple[PromptEvidence, ...],
        relationships: tuple[HostRelationship, ...] = (),
        citation_behavior: str = "cite material factual claims with evidence IDs",
    ) -> HostPromptContext:
        if decision.speaker_id != host.id:
            raise ValueError("director speaker does not match prompt host")
        evidence_by_id = {item.id: item for item in evidence}
        missing = [item for item in decision.evidence_ids if item not in evidence_by_id]
        if missing:
            raise ValueError(f"missing directed evidence IDs: {', '.join(missing)}")
        selected = tuple(evidence_by_id[item] for item in decision.evidence_ids)
        relevant_relationships = tuple(
            relationship.prompt_context()
            for relationship in relationships
            if relationship.from_host_id == host.id
        )
        system = "\n".join(
            (
                f"You are {host.display_name}, role: {host.role or 'host'}.",
                host.instructions.strip(),
                f"Director instruction: {decision.intent}",
                f"Turn target: about {decision.target_words} words / "
                f"{decision.target_duration_seconds} seconds.",
                f"Grounding: {citation_behavior}. Never invent evidence IDs or source claims.",
                "Use only evidence supplied in this turn for evidence-backed factual assertions.",
            )
        ).strip()
        context: dict[str, object] = {
            "host": {
                "id": host.id,
                "display_name": host.display_name,
                "role": host.role,
                "expertise": host.expertise,
                "behavior": dict(host.behavior),
                "evidence_priorities": list(host.evidence_priorities),
            },
            "director": {
                "intent": decision.intent,
                "handoff_instruction": decision.handoff_instruction,
                "target_words": decision.target_words,
                "target_duration_seconds": decision.target_duration_seconds,
            },
            "recent_dialogue": [
                {"speaker_id": turn.speaker_id, "text": turn.text} for turn in recent_dialogue
            ],
            "conversation_state": {
                "segment_ordinal": state.segment_ordinal,
                "segment_turn": state.segment_turn,
                "running_summary": state.running_summary,
                "unresolved_topics": list(state.unresolved_topics),
                "recent_context_refs": list(state.recent_context_refs),
                "participation": dict(state.participation),
            },
            "evidence": [
                {
                    "id": item.id,
                    "source_id": item.source_id,
                    "origin": item.origin,
                    "location": item.location,
                    "text": item.text,
                }
                for item in selected
            ],
            "relationships": list(relevant_relationships),
            "citation_behavior": citation_behavior,
        }
        return HostPromptContext(system=system, context=context)

    @staticmethod
    def as_json(prompt: HostPromptContext) -> str:
        """Return deterministic serialized context for provider/debug boundaries."""

        return json.dumps(prompt.context, sort_keys=True, separators=(",", ":"))
