"""Structured, secret-redacted diagnostics and support-bundle export."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

_SECRET_WORDS = frozenset({"authorization", "password", "cookie"})
_SECRET_PAIRS = frozenset(
    {
        ("api", "key"),
        ("access", "token"),
        ("refresh", "token"),
        ("client", "secret"),
        ("subscription", "key"),
        ("private", "key"),
        ("bearer", "token"),
    }
)
# Sanitize complete authorization values before generic assignment redaction.
# The delimiter preserves adjacent diagnostic fields (e.g. status=401).
# Digest can contain a comma-separated collection of credential components.
_AUTH_DIGEST = re.compile(r"(?i)(\bauthorization\s*[:=]\s*)digest\b[^;\r\n}\]]*")
# The two body alternatives must not overlap: a backslash is consumed only by the
# escape alternative, otherwise an unterminated quote backtracks exponentially.
_AUTH_QUOTED = re.compile(r"(?i)((['\"])authorization\2\s*:\s*)(['\"])(?:\\.|(?!\3)[^\\\r\n])*?\3")
# An opening quote with no closing quote on the line (a truncated or malformed
# diagnostic, including text cut by the length cap): redact to the end of the line.
_AUTH_QUOTED_OPEN = re.compile(
    r"(?im)((['\"])authorization\2\s*:\s*)(['\"])(?:\\.|(?!\3)[^\\\r\n])*(?=\r|\n|\Z)"
)
_AUTH_FIELD = re.compile(
    r"(?i)(\bauthorization\s*[:=]\s*)"
    # Opaque non-Digest credentials may include commas. Stop only at an
    # explicitly separated next diagnostic field, not every comma.
    r"(?:(?:\[REDACTED\])|(?!\s+[A-Za-z_][\w.-]*\s*[:=]|\s+https?://"
    r"|,\s+['\"]?[A-Za-z_][\w.-]*['\"]?\s*[:=]|[;}\]\r\n]).)+"
)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
# Bare provider API keys (``sk-...``, ``sk-ant-...``, ``sk-proj-...``) outside any
# ``key=value`` shape. The lookbehind keeps the scan linear on long runs.
_BARE_API_KEY = re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16,}")
_ASSIGNMENT = re.compile(
    # Diagnose unquoted dotted/bracketed/slashed keys with the same shared
    # key classifier used for quoted SDK mappings. Never depend on a small
    # allowlist of spellings that misses e.g. client.secret or api[key].
    r"(?i)(?<![A-Za-z0-9_.+/\[\]-])"
    # Avoid consuming noncredential wrapper fields surrounding nested secrets.
    r"(?=[A-Za-z0-9_.+/\[\]-]{1,128}\s*[:=])"
    r"([A-Za-z0-9_.+/\[\]-]*"
    r"(?:authorization|token|secret|password|cookie|api[-_.+/\[\]]*key)"
    r"[A-Za-z0-9_.+/\[\]-]*)(\s*[:=]\s*)([^\s,;]+)"
)
_QUOTED_MAPPING_ASSIGNMENT = re.compile(
    # Match a bounded, quoted mapping key and decide sensitivity with _is_secret_key.
    # Dots, slashes, brackets and plus signs must not bypass credential redaction.
    r"(?i)(['\"])([A-Za-z0-9_.+/\[\]-]{1,128})\1(\s*:\s*)(['\"])((?:\\.|(?!\4)[^\\\r\n])+)\4"
)
# SDK exceptions sometimes stringify header mappings whose sensitive values
# are nested lists, tuples, or dictionaries rather than quoted strings.
_QUOTED_CONTAINER_START = re.compile(r"(?i)(['\"])([A-Za-z0-9_.+/\[\]-]{1,128})\1(\s*:\s*)([\[({])")
# The lookbehind lets a scheme start only at a token boundary; without it every
# position inside a long alphanumeric run is retried, which is quadratic.
_URL_SCHEME_PREFIX = re.compile(r"(?i)(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://")
_USERINFO_WINDOW = 1024
_HOST_START = re.compile(r"[A-Za-z0-9._\[\]-]+(?::\d+)?(?:[/?#,]|$)")


def _split_userinfo(rest: str) -> tuple[int, int] | None:
    """Return ``(userinfo_end, host_start)`` for ``rest`` (text after ``scheme://``).

    ``rest`` is one whitespace-free window. Userinfo runs to the LAST ``@`` (as
    ``urlsplit`` does), so a password may itself contain ``@`` or ``/``. A ``/``
    before the first ``:`` means the text is a path, not userinfo; a ``/`` inside
    the password is accepted only when the "password" has no ``?`` (otherwise it
    is far more likely ``host:port/path?email=a@b``).
    """

    at = rest.rfind("@")
    if at == -1:
        return None
    userinfo = rest[:at]
    colon = userinfo.find(":")
    slash = userinfo.find("/")
    if colon == -1:
        if slash != -1:
            return None
    else:
        if slash != -1 and slash < colon:
            return None
        if slash != -1 and "?" in userinfo[colon:]:
            return None
    if _HOST_START.match(rest, at + 1) is None:
        return None
    return at, at + 1


def _redact_credential_urls(text: str) -> str:
    out: list[str] = []
    position = 0
    for scheme in _URL_SCHEME_PREFIX.finditer(text):
        if scheme.start() < position:
            continue
        window = text[scheme.end() : scheme.end() + _USERINFO_WINDOW]
        token = re.split(r"\s", window, maxsplit=1)[0]
        split = _split_userinfo(token)
        if split is None:
            continue
        out.append(text[position : scheme.end()])
        out.append("[REDACTED]@")
        position = scheme.end() + split[1]
    out.append(text[position:])
    return "".join(out)


# Linear-time tokenizer for http(s) URLs that were only partly percent-encoded
# (for example ``%23`` for ``#``); decoding is bounded in _redact_encoded_http_url.
_HTTP_URL_TOKEN = re.compile(r"(?i)(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://[^\s<>\"']+")
_CREDENTIAL_QUERY = re.compile(
    r"(?i)([?&;](?:api_key|apikey|key|token|access_token|auth|authorization|password|secret)=)"
    r"([^&#;\s]+)"
)
# A fragment ends at whitespace or a delimiter that closes a quoted/bracketed
# context, so surrounding JSON, Markdown and prose survive redaction.
# Earlier passes may already have inserted the ``[REDACTED]`` marker, so it is
# consumed as one unit rather than ending the fragment at its closing bracket.
_URL_SCHEME = re.compile(r"(?i)[a-z][a-z0-9+.-]*://")
_FRAGMENT_STOP = frozenset("\"'<>,")
_OPENERS = "([{"
_CLOSERS = ")]}"
_REDACTED_MARK = "[REDACTED]"


def _fragment_end(raw: str, start: int, enclosing: int) -> int:
    """Index just past the fragment that begins at ``raw[start]``.

    A fragment ends at whitespace, a quote, ``<``/``>`` or a comma. A closing
    bracket ends it only when an opener earlier on the line is still open
    (``[label](url#frag)``, ``(see url#frag)``); otherwise it is part of the value,
    so a secret containing ``)`` is not cut short. An earlier pass's
    ``[REDACTED]`` marker is consumed as one unit.
    """

    index = start
    length = len(raw)
    while index < length:
        char = raw[index]
        if raw.startswith(_REDACTED_MARK, index):
            index += len(_REDACTED_MARK)
            continue
        if char.isspace() or char in _FRAGMENT_STOP:
            break
        if char in _CLOSERS and enclosing > 0:
            break
        if char in _OPENERS:
            enclosing += 1
        index += 1
    return index


class _FragmentMatch:
    """A URL ``base#fragment`` occurrence, shaped like the ``re.Match`` it replaces."""

    __slots__ = ("_base", "_fragment", "end", "start")

    def __init__(self, start: int, end: int, base: str, fragment: str) -> None:
        self.start = start
        self.end = end
        self._base = base
        self._fragment = fragment

    def group(self, index: int) -> str:
        if index == 0:
            return f"{self._base}#{self._fragment}"
        return self._base if index == 1 else self._fragment


def _iter_url_fragments(text: str) -> Iterator[_FragmentMatch]:
    """Find ``scheme://base#fragment`` spans in one linear pass.

    Scanning whole URL tokens (instead of a regex anchored at every ``://``)
    keeps inputs such as ``"http://" * N`` linear; a per-start rescan was quadratic.
    The count of still-open brackets on the current line is carried across tokens
    so bracket handling stays linear too.
    """

    enclosing = 0
    cursor = 0
    for token in _HTTP_URL_TOKEN.finditer(text):
        enclosing = _advance_enclosing(text, cursor, token.start(), enclosing)
        cursor = token.start()
        raw = token.group(0)
        hash_index = raw.find("#")
        scheme = _URL_SCHEME.match(raw)
        if hash_index == -1 or scheme is None or hash_index <= scheme.end():
            continue
        end = _fragment_end(raw, hash_index + 1, enclosing)
        if end == hash_index + 1:
            continue
        yield _FragmentMatch(
            token.start(),
            token.start() + end,
            raw[:hash_index],
            raw[hash_index + 1 : end],
        )


def _advance_enclosing(text: str, start: int, stop: int, enclosing: int) -> int:
    """Bracket depth after ``text[start:stop]``; resets at a line break, never negative."""

    for char in text[start:stop]:
        if char == "\n":
            enclosing = 0
        elif char in _OPENERS:
            enclosing += 1
        elif char in _CLOSERS and enclosing > 0:
            enclosing -= 1
    return enclosing


def _sub_url_fragments(text: str) -> str:
    out: list[str] = []
    position = 0
    for match in _iter_url_fragments(text):
        out.append(text[position : match.start])
        out.append(_redact_url_fragment(match))
        position = match.end
    out.append(text[position:])
    return "".join(out)


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
        "code",
        "sig",
        "signature",
        "x-amz-signature",
        "x-goog-signature",
        "x-amz-credential",
        "x-amz-security-token",
        "session",
        "sessionid",
        "session_id",
        "sid",
        "jwt",
        "credential",
        "credentials",
        "pass",
        "passwd",
        "pwd",
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


_MAX_DECODE_LAYERS = 5


def _decode_layers(text: str) -> Iterator[str]:
    """Yield text, then each further percent-decoding of it, until stable or bounded.

    One shared bound for every layered-encoding check so SDK diagnostics that
    escape a URL repeatedly cannot hide credential keys from some passes only.
    """

    yield text
    for _ in range(_MAX_DECODE_LAYERS):
        decoded = unquote_plus(text)
        if decoded == text:
            return
        text = decoded
        yield text


def _redact_url_fragment(match: _FragmentMatch) -> str:
    # A diagnostic may contain a URL that was escaped multiple times by an SDK.
    # Bound decoding so layered percent-encoding cannot hide credential keys.
    for fragment in _decode_layers(match.group(2)):
        # Only ``key=value`` parts name a credential; a bare word is an anchor
        # (``#credentials``, ``#token-limits``) and stays readable.
        keys = [part.partition("=")[0] for part in re.split(r"[&;]", fragment) if "=" in part]
        if any(key.lower() in _SENSITIVE_URL_KEYS or _is_secret_key(key) for key in keys):
            return f"{match.group(1)}#[REDACTED]"
        # SDK diagnostics sometimes render fragment assignments as key:value.
        # Only treat a colon as a credential separator for known sensitive keys;
        # preserve benign anchors such as #section:overview.
        if any(
            ":" in part and is_sensitive_url_query_key(part.partition(":")[0])
            for part in re.split(r"[&;]", fragment)
        ):
            return f"{match.group(1)}#[REDACTED]"
    return match.group(0)


_MAX_NESTED_URL_DEPTH = 3
_nested_url_depth: ContextVar[int] = ContextVar("deeper_dive_nested_url_depth", default=0)


def _redact_encoded_http_url(match: re.Match[str]) -> str:
    """Inspect encoded endpoints without exposing their credential-bearing bytes."""
    original = match.group(0)
    # Handle ordinary and repeatedly percent-encoded URLs in SDK diagnostics.
    decoded = list(_decode_layers(original))[-1]
    if decoded == original:
        # Nothing was hidden by encoding (e.g. a bare ``%`` in a path): the other
        # passes already scanned this text, and re-scanning identical input would
        # recurse forever.
        return original
    if _URL_SCHEME.match(decoded) is None:
        return original
    depth = _nested_url_depth.get()
    if depth >= _MAX_NESTED_URL_DEPTH:
        # Deeply nested encodings cannot be inspected within a bounded budget;
        # fail closed rather than recurse without limit.
        return "[REDACTED]"
    token = _nested_url_depth.set(depth + 1)
    try:
        changed = _redact_text(decoded) != decoded
    finally:
        _nested_url_depth.reset(token)
    return "[REDACTED]" if changed else original


def _redact_partly_encoded_http_url(match: re.Match[str]) -> str:
    if "%" not in match.group(0):
        return match.group(0)
    return _redact_encoded_http_url(match)


def is_sensitive_url_query_key(key: str) -> bool:
    """Recognize credential query keys, including layered percent-encoding."""
    return any(
        layer.lower() in _SENSITIVE_URL_KEYS or _is_secret_key(layer)
        for layer in _decode_layers(key)
    )


def _redact_encoded_query(match: re.Match[str]) -> str:
    sensitive = is_sensitive_url_query_key(match.group(2))
    for nested in _decode_layers(match.group(4)):
        # Nested redirects may conceal credentials in userinfo or fragments,
        # not only in their query parameters. Preserve benign destinations.
        if "://" in nested and (
            _redact_credential_urls(nested) != nested
            or any(
                _redact_url_fragment(item) != item.group(0) for item in _iter_url_fragments(nested)
            )
            or any(
                is_sensitive_url_query_key(item.group(2))
                for item in _ENCODED_CREDENTIAL_QUERY.finditer(nested)
            )
        ):
            sensitive = True
            break
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


# Defense in depth against pathological inputs: redaction work grows with input
# size, so oversized strings are truncated (safely) before any pattern runs.
MAX_REDACTED_TEXT_CHARS = 262_144
_TRUNCATION_MARKER = "...[TRUNCATED]"


def _redact_text(value: str) -> str:
    """Apply every redaction pass in a fixed order.

    Order matters: quoted containers and auth headers first (they own their
    quotes), then URL fragments (before the greedy generic assignment pass),
    then assignments, plain and encoded credential queries, URL userinfo, and
    finally encoded/partly-encoded http(s) tokens, which re-enter this function.
    """

    if len(value) > MAX_REDACTED_TEXT_CHARS:
        value = value[:MAX_REDACTED_TEXT_CHARS] + _TRUNCATION_MARKER
    value = _redact_quoted_secret_containers(value)
    value = _AUTH_QUOTED.sub(
        lambda match: f"{match.group(1)}{match.group(3)}[REDACTED]{match.group(3)}",
        value,
    )
    value = _AUTH_QUOTED_OPEN.sub(
        lambda match: f"{match.group(1)}{match.group(3)}[REDACTED]",
        value,
    )
    value = _AUTH_DIGEST.sub(r"\1[REDACTED]", value)
    value = _AUTH_FIELD.sub(r"\1[REDACTED]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _BARE_API_KEY.sub("[REDACTED]", value)
    # Fragments run before the generic assignment pass, whose greedy value would
    # otherwise swallow the closing quote/bracket that delimits the URL.
    value = _sub_url_fragments(value)
    value = _QUOTED_MAPPING_ASSIGNMENT.sub(_redact_quoted_mapping_assignment, value)
    value = _ASSIGNMENT.sub(_redact_assignment, value)
    value = _CREDENTIAL_QUERY.sub(r"\1[REDACTED]", value)
    value = _ENCODED_CREDENTIAL_QUERY.sub(_redact_encoded_query, value)
    value = _redact_credential_urls(value)
    value = _ENCODED_HTTP_URL.sub(_redact_encoded_http_url, value)
    return _HTTP_URL_TOKEN.sub(_redact_partly_encoded_http_url, value)


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
