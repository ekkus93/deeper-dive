"""Structured, secret-redacted diagnostics and support-bundle export."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_SECRET_KEY = re.compile(r"(authorization|api[-_]?key|token|secret|password|cookie)", re.I)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|api[-_]?key|token|secret|password|cookie)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_CREDENTIAL_URL = re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@")


def _redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
    return _CREDENTIAL_URL.sub(r"\1[REDACTED]@", value)


def redact(value: object) -> object:
    """Recursively redact credentials while preserving useful diagnostic shape."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    level: str
    event: str
    run_id: str | None = None
    provider: str | None = None
    message: str = ""
    details: Mapping[str, object] | None = None

    def payload(self) -> dict[str, object]:
        return redact(asdict(self))  # type: ignore[return-value]


class StructuredDiagnosticLog:
    """Small JSON-lines logger suitable for application and provider diagnostics."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def emit(self, event: DiagnosticEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.payload(), sort_keys=True) + "\n")


def sanitize_provider_error(
    provider: str, exc: BaseException, *, run_id: str | None = None
) -> DiagnosticEvent:
    """Return a support-safe provider failure without headers or credential values."""
    return DiagnosticEvent(
        level="error",
        event="provider_error",
        run_id=run_id,
        provider=provider,
        message=str(redact(str(exc))),
    )


def export_diagnostic_bundle(
    destination: Path,
    *,
    run_id: str | None = None,
    provider_diagnostics: Mapping[str, object] | None = None,
    configuration: Mapping[str, object] | None = None,
    source_excerpts: Mapping[str, str] | None = None,
    include_source_excerpts: bool = False,
) -> Path:
    """Export sanitized diagnostics; source contents require explicit opt-in."""
    payload: dict[str, Any] = {
        "run_id": run_id,
        "provider_diagnostics": redact(provider_diagnostics or {}),
        "configuration": redact(configuration or {}),
        "source_excerpts_included": bool(include_source_excerpts and source_excerpts),
    }
    if include_source_excerpts and source_excerpts:
        payload["source_excerpts"] = redact(source_excerpts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination
