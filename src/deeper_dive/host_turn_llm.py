"""LLM-backed host-turn provider used by production conversation generation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from deeper_dive.director_decision import DirectorDecision
from deeper_dive.llm import LLMMessage, LLMProvider, LLMRequest


@dataclass(frozen=True, slots=True)
class LLMHostTurnProvider:
    """Adapt the normalized LLM boundary to the HostTurnProvider contract."""

    provider: LLMProvider
    model: str

    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
        request_payload = {
            "speaker_id": decision.speaker_id,
            "intent": decision.intent,
            "target_words": decision.target_words,
            "target_duration_seconds": decision.target_duration_seconds,
            "evidence_ids": list(decision.evidence_ids),
        }
        response = self.provider.generate(
            LLMRequest(
                messages=(
                    LLMMessage(
                        "system",
                        "Generate one podcast host turn. Return only a JSON object with "
                        "speaker_id, text, and evidence_ids. The speaker_id must match the "
                        "request and evidence_ids must be selected only from the supplied IDs.",
                    ),
                    LLMMessage("user", json.dumps(request_payload, sort_keys=True)),
                ),
                model=self.model,
                response_schema={
                    "type": "object",
                    "required": ["speaker_id", "text", "evidence_ids"],
                    "properties": {
                        "speaker_id": {"type": "string"},
                        "text": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    },
                },
            )
        )
        payload: object = response.structured
        if payload is None:
            try:
                payload = json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise ValueError("host-generation provider returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("host-generation provider returned a non-object response")
        speaker_id = payload.get("speaker_id")
        text = payload.get("text")
        evidence_ids = payload.get("evidence_ids")
        if not isinstance(speaker_id, str) or not speaker_id.strip():
            raise ValueError("host-generation response requires speaker_id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("host-generation response requires non-empty text")
        if not isinstance(evidence_ids, list) or not all(
            isinstance(value, str) for value in evidence_ids
        ):
            raise ValueError("host-generation response requires string evidence_ids")
        return {
            "speaker_id": speaker_id,
            "text": text,
            "evidence_ids": evidence_ids,
        }
