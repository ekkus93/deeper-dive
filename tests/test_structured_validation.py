from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from deeper_dive.structured_validation import (
    StructuredValidationError,
    ValidationFailureStore,
    validate_structured_output,
)


class Plan(BaseModel):
    title: str
    segments: list[str]


def test_valid_output_returns_durable_ready_model() -> None:
    result = validate_structured_output('{"title":"T","segments":["A"]}', Plan)
    assert result == Plan(title="T", segments=["A"])


def test_invalid_output_is_repaired_with_bounded_attempts(tmp_path) -> None:
    calls: list[int] = []
    store = ValidationFailureStore(tmp_path / "diagnostics" / "validation.jsonl")

    def repair(raw: str, error: str, attempt: int) -> str:
        calls.append(attempt)
        assert error
        return '{"title":"fixed","segments":["one"]}'

    result = validate_structured_output(
        '{"title":7}', Plan, repair=repair, max_repairs=2, failure_store=store
    )
    assert result.title == "fixed"
    assert calls == [1]
    records = [json.loads(line) for line in store.path.read_text().splitlines()]
    assert records[0]["attempt"] == 1
    assert "segments" in records[0]["error"]
    assert '{"title":7}' not in store.path.read_text()


def test_invalid_objects_never_escape_validation_or_exceed_repair_bound(tmp_path) -> None:
    calls = 0

    def bad_repair(raw: str, error: str, attempt: int) -> str:
        nonlocal calls
        calls += 1
        return "still invalid"

    with pytest.raises(StructuredValidationError):
        validate_structured_output("invalid", Plan, repair=bad_repair, max_repairs=2)
    assert calls == 2


def test_negative_repair_bound_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_repairs"):
        validate_structured_output("{}", Plan, max_repairs=-1)
