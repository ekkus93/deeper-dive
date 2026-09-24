from __future__ import annotations

import json

import pytest

from deeper_dive.director_decision import DirectorDecision
from deeper_dive.host_turn_llm import LLMHostTurnProvider
from deeper_dive.llm import FakeLLMProvider


def test_llm_host_turn_provider_routes_structured_request_to_configured_model() -> None:
    response = json.dumps(
        {
            "speaker_id": "host-a",
            "text": "provider-backed unique turn marker",
            "evidence_ids": ["claim-1"],
        }
    )
    llm = FakeLLMProvider(provider_id="configured", model="host-model", response=response)
    adapter = LLMHostTurnProvider(llm, "host-model")
    decision = DirectorDecision(
        speaker_id="host-a",
        intent="Explain the evidence",
        target_duration_seconds=30,
        target_words=60,
        evidence_ids=("claim-1", "claim-2"),
    )

    payload = adapter.generate_turn(decision)

    assert payload["text"] == "provider-backed unique turn marker"
    assert payload["evidence_ids"] == ["claim-1"]
    assert len(llm.requests) == 1
    request = llm.requests[0]
    assert request.model == "host-model"
    assert request.response_schema is not None
    assert "Explain the evidence" in request.messages[-1].content


def test_llm_host_turn_provider_rejects_malformed_provider_output() -> None:
    llm = FakeLLMProvider(response="not-json")
    adapter = LLMHostTurnProvider(llm, "fake-v1")
    decision = DirectorDecision(
        speaker_id="host-a", intent="Discuss", target_duration_seconds=30, target_words=60
    )

    with pytest.raises(ValueError, match="invalid JSON"):
        adapter.generate_turn(decision)


def test_llm_host_turn_provider_rejects_invalid_structured_shape() -> None:
    llm = FakeLLMProvider(response=json.dumps({"speaker_id": "host-a", "text": "turn"}))
    adapter = LLMHostTurnProvider(llm, "fake-v1")
    decision = DirectorDecision(
        speaker_id="host-a", intent="Discuss", target_duration_seconds=30, target_words=60
    )

    with pytest.raises(ValueError, match="evidence_ids"):
        adapter.generate_turn(decision)
