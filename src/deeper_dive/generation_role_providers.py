"""LLM-backed role adapters for conversation directing and verification."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from deeper_dive.director_decision import DirectorDecision
from deeper_dive.host_turn import HostTurn
from deeper_dive.llm import LLMMessage, LLMProvider, LLMRequest


@dataclass(frozen=True, slots=True)
class LLMDirectorDecisionProvider:
    """Adapt a configured LLM provider to durable director decisions."""

    provider: LLMProvider
    model: str

    def decide(
        self,
        *,
        episode_title: str,
        host_ids: tuple[str, ...],
        available_evidence_ids: tuple[str, ...] = (),
    ) -> DirectorDecision:
        response = self.provider.generate(
            LLMRequest(
                messages=(
                    LLMMessage(
                        "system",
                        "Choose the next podcast host turn as a director decision. "
                        "Return only JSON with speaker_id, intent, evidence_ids, "
                        "target_duration_seconds, target_words, handoff_instruction, "
                        "and segment_signal.",
                    ),
                    LLMMessage(
                        "user",
                        json.dumps(
                            {
                                "episode_title": episode_title,
                                "host_ids": list(host_ids),
                                "available_evidence_ids": list(available_evidence_ids),
                            },
                            sort_keys=True,
                        ),
                    ),
                ),
                model=self.model,
                response_schema={
                    "type": "object",
                    "required": ["speaker_id", "intent", "evidence_ids"],
                    "properties": {
                        "speaker_id": {"type": "string"},
                        "intent": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "target_duration_seconds": {"type": "integer"},
                        "target_words": {"type": "integer"},
                        "handoff_instruction": {"type": "string"},
                        "segment_signal": {"type": "string"},
                    },
                },
            )
        )
        payload = _object_payload(
            response.structured,
            response.text,
            role="directing",
        )
        return DirectorDecision.from_payload(
            dict(payload),
            participating_host_ids=host_ids,
            available_evidence_ids=available_evidence_ids,
        )


@dataclass(frozen=True, slots=True)
class LLMTranscriptVerifier:
    """Adapt a configured LLM provider to transcript verification."""

    provider: LLMProvider
    model: str

    def verify(self, *, episode_id: str, turns: tuple[HostTurn, ...]) -> None:
        response = self.provider.generate(
            LLMRequest(
                messages=(
                    LLMMessage(
                        "system",
                        "Verify generated podcast transcript quality and scope. "
                        "Return only JSON with accepted boolean and optional notes.",
                    ),
                    LLMMessage(
                        "user",
                        json.dumps(
                            {
                                "episode_id": episode_id,
                                "turns": [
                                    {
                                        "speaker_id": turn.speaker_id,
                                        "text": turn.text,
                                        "evidence_ids": list(turn.evidence_ids),
                                    }
                                    for turn in turns
                                ],
                            },
                            sort_keys=True,
                        ),
                    ),
                ),
                model=self.model,
                response_schema={
                    "type": "object",
                    "required": ["accepted"],
                    "properties": {
                        "accepted": {"type": "boolean"},
                        "notes": {"type": "string"},
                    },
                },
            )
        )
        payload = _object_payload(
            response.structured,
            response.text,
            role="verification",
        )
        accepted = payload.get("accepted")
        if not isinstance(accepted, bool):
            raise ValueError("verification provider response requires accepted boolean")
        if not accepted:
            notes = payload.get("notes")
            suffix = f": {notes}" if isinstance(notes, str) and notes.strip() else ""
            raise ValueError(f"verification provider rejected transcript{suffix}")


def _object_payload(
    structured: Mapping[str, object] | None,
    text: str,
    *,
    role: str,
) -> Mapping[str, object]:
    payload: object = structured
    if payload is None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{role} provider returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{role} provider returned a non-object response")
    return payload
