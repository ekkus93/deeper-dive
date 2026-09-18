"""Centralized Pydantic validation and bounded structured-output repair."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

Repair = Callable[[str, str, int], str]


class StructuredValidationError(ValueError):
    """Raised only after all bounded validation/repair attempts fail."""


@dataclass(frozen=True, slots=True)
class ValidationFailure:
    attempt: int
    error: str


class ValidationFailureStore:
    """Append-only sanitized JSONL diagnostics; response content is never persisted."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, failure: ValidationFailure) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"attempt": failure.attempt, "error": _sanitize(failure.error)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def validate_structured_output[T: BaseModel](
    raw: str,
    model_type: type[T],
    *,
    repair: Repair | None = None,
    max_repairs: int = 1,
    failure_store: ValidationFailureStore | None = None,
) -> T:
    """Validate JSON into a model, optionally repairing invalid output a bounded number of times."""

    if max_repairs < 0:
        raise ValueError("max_repairs must not be negative")
    candidate = raw
    failures: list[ValidationFailure] = []
    for attempt in range(max_repairs + 1):
        try:
            return model_type.model_validate_json(candidate)
        except (ValidationError, ValueError) as exc:
            failure = ValidationFailure(attempt + 1, str(exc))
            failures.append(failure)
            if failure_store is not None:
                failure_store.append(failure)
            if repair is None or attempt >= max_repairs:
                break
            candidate = repair(candidate, _sanitize(str(exc)), attempt + 1)
    summary = "; ".join(_sanitize(item.error) for item in failures)
    raise StructuredValidationError(f"structured output validation failed: {summary}")


def _sanitize(value: str) -> str:
    """Bound diagnostic size and remove control characters/newlines."""

    compact = " ".join(value.split())
    return compact[:1000]
