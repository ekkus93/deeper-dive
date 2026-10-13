"""Structured, secret-redacted diagnostics and support-bundle export."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote_plus

_SECRET_WORDS = frozenset({"authorization", "password", "cookie"})
_SECRET_PAIRS = frozenset(
    {
        ("api", "key"),
        ("access", "token"),
        ("refresh", "token"),
        ("client", "secret"),
        ("bearer", "token"),
    }
)
# Sanitize complete authorization values before generic assignment redaction.
# The delimiter preserves adjacent diagnostic fields (e.g. status=401).
# Digest can contain a comma-separated collection of credential components.
_AUTH_DIGEST = re.compile(r"(?i)(\bauthorization\s*[:=]\s*)digest\b[^;\r\n}\]]*")
_AUTH_QUOTED = re.compile(r"(?i)((['\"])authorization\2\s*:\s*)(['\"])(?:\\.|(?!\3).)*?\3")
_AUTH_FIELD = re.compile(
    r"(?i)(\bauthorization\s*[:=]\s*)"
    # Opaque non-Digest credentials may include commas. Stop only at an
    # explicitly separated next diagnostic field, not every comma.
    r"(?:(?:\[REDACTED\])|(?!\s+[A-Za-z_][\w.-]*\s*[:=]|\s+https?://"
    r"|,\s+['\"]?[A-Za-z_][\w.-]*['\"]?\s*[:=]|[;}\]\r\n]).)+"
)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT = re.compile(
    # Diagnose unquoted dotted/bracketed/slashed keys with the same shared
    # key classifier used for quoted SDK mappings. Never depend on a small
    # allowlist of spellings that misses e.g. client.secret or api[key].
    r"(?i)(?<![A-Za-z0-9_.+/\[\]-])([A-Za-z0-9_.+/\[\]-]{1,128})"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_QUOTED_MAPPING_ASSIGNMENT = re.compile(
    # Match a bounded, quoted mapping key and decide sensitivity with _is_secret_key.
    # Dots, slashes, brackets and plus signs must not bypass credential redaction.
    r"(?i)(['\"])([A-Za-z0-9_.+/\[\]-]{1,128})\1(\s*:\s*)(['\"])((?:\\.|(?!\4)[^\\\r\n])+)\4"
)
# SDK exceptions sometimes stringify header mappings whose sensitive values
# are nested lists, tuples, or dictionaries rather than quoted strings.
_QUOTED_CONTAINER_START = re.compile(r"(?i)(['\"])([A-Za-z0-9_.+/\[\]-]{1,128})\1(\s*:\s*)([\[({])")
_CREDENTIAL_URL = re.compile(r"(?i)(https?://)([^/@\s:]+)(?::([^/@\s]+))?@")
_CREDENTIAL_QUERY = re.compile(
    r"(?i)([?&;](?:api_key|apikey|key|token|access_token|auth|authorization|password|secret)=)"
    r"([^&#;\s]+)"
)
_URL_FRAGMENT = re.compile(r"(?i)(https?://[^\s#]+)#([^\s]+)")
# Some SDKs percent-encode the entire endpoint in error and redirect fields.
_ENCODED_HTTP_URL = re.compile(r"(?i)https?%(?:25)*3a%(?:25)*2f%(?:25)*2f[^\s<>\"']+")
# Percent-encoded credential *keys* in URL queries are not matched by the
# plain-text assignment pattern. Decode only the key and retain the URL shape.
# Match raw punctuation in keys (api[key], api+key, api/key) as well as
# percent-encoded spelling. Treat legacy semicolons as query separators,
# including when an earlier non-sensitive parameter precedes the secret.
# The shared key classifier decides sensitivity.
_ENCODED_CREDENTIAL_QUERY = re.compile(r"(?i)([?&;])([^?&#=;\s]+)(=)([^&#;\s]+)")
_SENSITIVE_URL_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "key",
        "token",
        "access_token",
        "auth",
        "authorization",
        "password",
        "secret",
    }
)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD_SPLIT = re.compile(r"[^A-Za-z0-9]+")


def _key_words(key: object) -> tuple[str, ...]:
    separated = _CAMEL_BOUNDARY.sub("_", str(key))
    return tuple(part.lower() for part in _WORD_SPLIT.split(separated) if part)


def _is_secret_key(key: object) -> bool:
    words = _key_words(key)
    if not words:
        return False
    if "token" in words or "secret" in words:
        return True
    if any(word in _SECRET_WORDS for word in words):
        return True
    return any(pair in zip(words, words[1:], strict=False) for pair in _SECRET_PAIRS)


def _redact_assignment(match: re.Match[str]) -> str:
    if not _is_secret_key(match.group(1)):
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}[REDACTED]"


def _redact_quoted_mapping_assignment(match: re.Match[str]) -> str:
    if not _is_secret_key(match.group(2)):
        return match.group(0)
    return (
        f"{match.group(1)}{match.group(2)}{match.group(1)}"
        f"{match.group(3)}{match.group(4)}[REDACTED]{match.group(4)}"
    )


def _redact_url_fragment(match: re.Match[str]) -> str:
    # A diagnostic may contain a URL that was escaped multiple times by an SDK.
    # Bound decoding so layered percent-encoding cannot hide credential keys.
    fragment = match.group(2)
    for _ in range(4):
        try:
            pairs = parse_qsl(fragment.replace(";", "&"), keep_blank_values=True)
        except ValueError:
            pairs = []
        if any(key.lower() in _SENSITIVE_URL_KEYS or _is_secret_key(key) for key, _ in pairs):
            return f"{match.group(1)}#[REDACTED]"
        # SDK diagnostics sometimes render fragment assignments as key:value.
        # Only treat a colon as a credential separator for known sensitive keys;
        # preserve benign anchors such as #section:overview.
        if any(
            ":" in part and is_sensitive_url_query_key(part.partition(":")[0])
            for part in re.split(r"[&;]", fragment)
        ):
            return f"{match.group(1)}#[REDACTED]"
        decoded = unquote_plus(fragment)
        if decoded == fragment:
            break
        fragment = decoded
    return match.group(0)


def _redact_encoded_http_url(match: re.Match[str]) -> str:
    """Inspect encoded endpoints without exposing their credential-bearing bytes."""
    original = match.group(0)
    decoded = original
    # Handle ordinary and repeatedly percent-encoded URLs in SDK diagnostics.
    for _ in range(5):
        updated = unquote_plus(decoded)
        if updated == decoded:
            break
        decoded = updated
    if decoded.lower().startswith(("http://", "https://")) and _redact_text(decoded) != decoded:
        return "[REDACTED]"
    return original


def is_sensitive_url_query_key(key: str) -> bool:
    """Recognize credential query keys, including layered percent-encoding."""
    for _ in range(4):
        if key.lower() in _SENSITIVE_URL_KEYS or _is_secret_key(key):
            return True
        decoded = unquote_plus(key)
        if decoded == key:
            break
        key = decoded
    return key.lower() in _SENSITIVE_URL_KEYS or _is_secret_key(key)


def _redact_encoded_query(match: re.Match[str]) -> str:
    sensitive = is_sensitive_url_query_key(match.group(2))
    nested = match.group(4)
    for _ in range(5):
        # Nested redirects may conceal credentials in userinfo or fragments,
        # not only in their query parameters. Preserve benign destinations.
        if "://" in nested and (
            _CREDENTIAL_URL.search(nested)
            or any(
                _redact_url_fragment(item) != item.group(0)
                for item in _URL_FRAGMENT.finditer(nested)
            )
            or any(
                is_sensitive_url_query_key(item.group(2))
                for item in _ENCODED_CREDENTIAL_QUERY.finditer(nested)
            )
        ):
            sensitive = True
            break
        decoded = unquote_plus(nested)
        if decoded == nested:
            break
        nested = decoded
    if sensitive:
        return f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]"
    return match.group(0)


def _redact_quoted_secret_containers(value: str) -> str:
    """Remove nested list/dict values of sensitive keys in stringified SDK errors.

    Boundaries are matched while respecting quoted delimiters, so an embedded
    ']' or '}' inside a quoted credential cannot truncate redaction. For
    malformed/unclosed containers, conservatively remove the remaining text.
    """
    pieces: list[str] = []
    position = 0
    for match in _QUOTED_CONTAINER_START.finditer(value):
        if match.start() < position or not _is_secret_key(match.group(2)):
            continue
        opening = match.end() - 1
        pending = [{"[": "]", "{": "}", "(": ")"}[value[opening]]]
        quote: str | None = None
        escaped = False
        end = len(value)
        for index in range(opening + 1, len(value)):
            char = value[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in {"'", '"'}:
                quote = char
            elif char in "[{(":
                pending.append({"[": "]", "{": "}", "(": ")"}[char])
            elif char in "]})":
                if char != pending[-1]:
                    break
                pending.pop()
                if not pending:
                    end = index + 1
                    break
        pieces.append(value[position : match.start()])
        pieces.append(value[match.start() : opening] + "[REDACTED]")
        position = end
    pieces.append(value[position:])
    return "".join(pieces)


def _redact_text(value: str) -> str:
    value = _redact_quoted_secret_containers(value)
    value = _AUTH_QUOTED.sub(
        lambda match: f"{match.group(1)}{match.group(3)}[REDACTED]{match.group(3)}",
        value,
    )
    value = _AUTH_DIGEST.sub(r"\1[REDACTED]", value)
    value = _AUTH_FIELD.sub(r"\1[REDACTED]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _QUOTED_MAPPING_ASSIGNMENT.sub(_redact_quoted_mapping_assignment, value)
    value = _ASSIGNMENT.sub(_redact_assignment, value)
    value = _URL_FRAGMENT.sub(_redact_url_fragment, value)
    value = _CREDENTIAL_QUERY.sub(r"\1[REDACTED]", value)
    value = _ENCODED_CREDENTIAL_QUERY.sub(_redact_encoded_query, value)
    value = _CREDENTIAL_URL.sub(r"\1[REDACTED]@", value)
    return _ENCODED_HTTP_URL.sub(_redact_encoded_http_url, value)


def redact(value: object, *, drop_secret_keys: bool = False) -> object:
    """Recursively redact credentials while preserving useful diagnostic shape."""
    if isinstance(value, Mapping):
        return {
            str(redact(str(key))): (
                "[REDACTED]"
                if _is_secret_key(key)
                else redact(item, drop_secret_keys=drop_secret_keys)
            )
            for key, item in value.items()
            if not (drop_secret_keys and _is_secret_key(key))
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, drop_secret_keys=drop_secret_keys) for item in value]
    if isinstance(value, (set, frozenset)):
        return [redact(item, drop_secret_keys=drop_secret_keys) for item in sorted(value, key=repr)]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def sanitize_exception_message(exc: BaseException) -> str:
    """Return a redacted exception message including sanitized chained context."""

    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(redact(str(current))))
        if current.__cause__ is not None:
            parts.append("caused by:")
            current = current.__cause__
        elif current.__context__ is not None and not current.__suppress_context__:
            parts.append("context:")
            current = current.__context__
        else:
            current = None
    return " | ".join(part for part in parts if part)


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
        message=sanitize_exception_message(exc),
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
