"""Structured, secret-redacted diagnostics and support-bundle export."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, unquote_plus

_CREDENTIAL_NOUNS = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwd",
        "pwd",
        "pass",
        "passphrase",
        "auth",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "session",
        "sessionid",
        "apikey",
        "accesstoken",
        "clientsecret",
        "privatekey",
        "signature",
        "jwt",
    }
)
_CREDENTIAL_PAIRS = frozenset(
    {
        ("api", "key"),
        ("access", "token"),
        ("refresh", "token"),
        ("client", "secret"),
        ("subscription", "key"),
        ("private", "key"),
        ("bearer", "token"),
        ("session", "id"),
    }
)
# Generic query names are sensitive only in a URL query/fragment context. A plain
# ``key=value`` or ``--key value`` is not treated as a credential by the shared noun set.
_QUERY_ONLY_GENERIC_NAMES = frozenset({"key", "code", "sig", "sid"})
_CREDENTIAL_SUFFIXES = frozenset(
    {"token", "secret", "apikey", "accesstoken", "clientsecret", "privatekey", "sessionid"}
)


def _credential_alternation() -> str:
    separator = r"[-_.+/\[\]]*"
    spellings = [re.escape(noun) for noun in _CREDENTIAL_NOUNS]
    spellings.extend(separator.join(re.escape(word) for word in pair) for pair in _CREDENTIAL_PAIRS)
    return "|".join(sorted(spellings, key=len, reverse=True))


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
    r"([A-Za-z0-9_.+/\[\]-]*(?:" + _credential_alternation() + r")"
    r"[A-Za-z0-9_.+/\[\]-]*)(\s*[:=]\s*)([^\s,;]+)"
)
_QUOTED_MAPPING_ASSIGNMENT = re.compile(
    # Match a bounded, quoted mapping key and decide sensitivity with _is_secret_key.
    # Dots, slashes, brackets and plus signs must not bypass credential redaction.
    r"(?i)(['\"])([A-Za-z0-9_.+/\[\]-]{1,128})\1(\s*:\s*b?)(['\"])((?:\\.|(?!\4)[^\\\r\n])+)\4"
)
# A secret value whose closing quote is missing (truncated or malformed text): redact to
# the end of the line. Possessive, so a long unterminated value is scanned once.
_QUOTED_MAPPING_OPEN = re.compile(
    r"(?i)(['\"])([A-Za-z0-9_.+/\[\]-]{1,128})\1(\s*:\s*b?)(['\"])(?:\\.|(?!\4)[^\\\r\n])*+(?=\r|\n|\Z)"
)
# ``('x-api-key', 'C')`` / ``(b'authorization', b'Basic C')``: header lists and tuples
# stringified by an SDK. The classifier decides which keys are sensitive.
_TUPLE_PAIR = re.compile(
    r"(?i)([\[(]\s*b?)(['\"])([A-Za-z0-9_.+/\[\]-]{1,128})\2(\s*,\s*b?)(['\"])"
    r"((?:\\.|(?!\5)[^\\\r\n])+)\5"
)
# ``--api-key C``: a CLI flag and its value separated by whitespace.
_CLI_FLAG_VALUE = re.compile(r"(?<![\w-])(--?[A-Za-z][A-Za-z0-9_.-]{0,127})([ \t]+)(?!-)(\S+)")
# ``<password>C</password>``.
_XML_ELEMENT = re.compile(
    r"(?i)(<)([A-Za-z][A-Za-z0-9_.:-]{0,127})((?:\s[^<>]{0,256})?>)([^<>]{1,2048})(</\2\s*>)"
)
# ``password="pa ss"``: an unquoted key with a quoted value that may hold spaces. A missing
# closing quote (truncated text) redacts to the end of the line.
_QUOTED_VALUE_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9_.+/\[\]-])([A-Za-z0-9_.+/\[\]-]{1,128})(\s*[:=]\s*)(['\"])"
    r"(?:\\.|(?!\3)[^\\\r\n])*+(?:\3|(?=\r|\n|\Z))"
)
# ``\"apiKey\":\"C\"`` inside a JSON string. The value is bounded so a repeated prefix
# cannot make the scan quadratic.
_ESCAPED_QUOTE_PAIR = re.compile(
    r"(?i)(?<!\\)(\\{1,8}['\"])([A-Za-z0-9_.+/\[\]-]{1,128})\1(\s*:\s*)(\\{1,8}['\"])"
    r"((?:(?!(?<!\\)\4)[^\r\n]){0,2048}+)((?<!\\)\4|(?=\r|\n|\Z))"
)
# The opener must be followed by a line break, an escaped ``\\n`` or a base64-looking run, so
# prose that merely names the header (``use '-----BEGIN PRIVATE KEY-----' header``) survives.
_PEM_PRIVATE_KEY = re.compile(
    r"(?i)-----BEGIN [A-Z ]{0,40}PRIVATE KEY(?: BLOCK)?-----"
    r"(?=[ \t]*(?:[\r\n\x0b\x0c\x85\u2028\u2029]|\\[nr]|<br|%0[ad]|[A-Za-z0-9+/=:]{16}))"
    r".*?"
    r"(?:-----END [A-Z ]{0,40}PRIVATE KEY(?: BLOCK)?-----|\Z)",
    re.S,
)
# SDK exceptions sometimes stringify header mappings whose sensitive values
# are nested lists, tuples, or dictionaries rather than quoted strings.
_QUOTED_CONTAINER_START = re.compile(r"(?i)(['\"])([A-Za-z0-9_.+/\[\]-]{1,128})\1(\s*:\s*)([\[({])")
# The lookbehind lets a scheme start only at a token boundary; without it every
# position inside a long alphanumeric run is retried, which is quadratic.
_URL_SCHEME_PREFIX = re.compile(r"(?i)(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://")
_USERINFO_WINDOW = 1024
# The authority of a URL ends at the first path, query, fragment, whitespace or quote.
_AUTHORITY = re.compile(r"[^\s/?#\"'<>]*")
_HOST_CHAR = re.compile(r"[\w.\[\]$-]")


# A scan token ends at whitespace, at a ``,``/``)`` that is followed by whitespace, a
# quote, a closing bracket, another separator or the end, and at a quote that is
# followed by such a separator. A password may therefore contain ``,``, ``)`` and
# quotes (``pa,ss``, ``pa'ss``), while JSON or code that merely follows a URL
# (``"https://h/x", "e": "a@b"``) still ends the token.
_TOKEN_END = re.compile(r"""\s|[,)](?=[\s"'}\],;:)]|\Z)|["'](?=[\s,)}\];:]|\Z)""")
_UNTIL_WHITESPACE = re.compile(r"\S*")
_USERINFO_TERMINATORS = "/?#"
# ``host:port`` followed by a terminator: a port is 1-5 digits (at most 65535).
_PORT_THEN_TERMINATOR = re.compile(r"(\d{1,5})(?=[/?#'\"<>]|\Z)")


def _credential_shaped(userinfo: str) -> bool:
    """Whether ``userinfo`` (the text before a candidate ``@``) looks like ``user:password``.

    The ``:`` must come before the first ``/``, ``?`` or ``#`` (otherwise it belongs to
    a query or path such as ``example.com?q=a:b@c``). A trailing slash is accepted only
    when the username before the colon has no slash or dot, preserving host paths such as
    ``repo/@v1`` and ``host:8080/@x``. What follows the colon must not be a port number
    directly followed by a terminator: ``host:8080?email=a@b`` and
    ``host:8080/v1/models/gpt@latest`` are a host, a port and a path.
    """

    colon = userinfo.find(":")
    if colon == -1:
        return False
    username = userinfo[:colon]
    if userinfo.endswith("/") and ("/" in username or "." in username):
        return False
    first_terminator = min(
        (index for index in map(userinfo.find, _USERINFO_TERMINATORS) if index != -1),
        default=len(userinfo),
    )
    if colon > first_terminator:
        return False
    port = _PORT_THEN_TERMINATOR.match(userinfo, colon + 1)
    return port is None or int(port.group(1)) > 65535


def _userinfo_end(text: str, start: int) -> int | None:
    """Index of the ``@`` that closes the userinfo of the URL whose authority starts at ``start``.

    1. Authority form (``user:pw@host``): the LAST ``@`` inside the authority, as
       ``urlsplit`` does, so a password may contain ``@``. The authority ends at the
       first ``/``, ``?``, ``#``, whitespace or quote.
    2. Terminator-in-password form (``user:pa#ss@host``, ``app:ab/cd?e@db``,
       ``u:pa'ss@h``): the LAST ``@`` of the scan token (see ``_TOKEN_END``) that is
       followed by a host character and whose preceding text is ``_credential_shaped``.
       A password ending in ``/`` is accepted only when its username has no slash or dot;
       this catches ``user:p/CANARY/@host`` while preserving path forms such as
       ``repo/@v1`` and ``host:8080/@x``.
       It also extends an authority-form match when the password itself contained an
       ``@`` and a terminator (``user:p@a#ss@host``): the later ``@`` wins, because
       over-redacting a URL tail is safe and a leaked password is not.
    3. Fail closed: when the token fills the whole scan window (a password longer than
       ``_USERINFO_WINDOW`` containing a terminator) and is credential-shaped, the
       whole whitespace-delimited token is redacted.

    Accepted gaps (``tests/test_fourth_post_review_sanitizer_matrix.py``): a password
    that starts with a valid port number directly followed by a terminator
    (``u:8#pw@h``, ``u:2024#Summer@h``) is indistinguishable from
    ``host:8080#mail@b.com`` and is not redacted. Over-redaction (never a leak):
    ``https://user:pw@host:8080/x?e=a@b`` loses its host and path.
    """

    authority = _AUTHORITY.match(text, start)
    assert authority is not None
    authority_at = text.rfind("@", start, authority.end())
    window = text[start : start + _USERINFO_WINDOW]
    end_match = _TOKEN_END.search(window)
    token = window if end_match is None else window[: end_match.start()]
    at = token.rfind("@")
    credential = (
        at != -1 and _HOST_CHAR.match(token, at + 1) is not None and _credential_shaped(token[:at])
    )
    if credential and (authority_at == -1 or start + at > authority_at):
        return start + at
    if authority_at != -1:
        return authority_at
    if end_match is None and len(window) == _USERINFO_WINDOW and _credential_shaped(token):
        whole = _UNTIL_WHITESPACE.match(text, start)
        assert whole is not None
        return whole.end() - 1
    return None


def _redact_credential_urls(text: str) -> str:
    out: list[str] = []
    position = 0
    for scheme in _URL_SCHEME_PREFIX.finditer(text):
        if scheme.start() < position:
            continue
        at = _userinfo_end(text, scheme.end())
        if at is None:
            continue
        out.append(text[position : scheme.end()])
        out.append("[REDACTED]@")
        position = at + 1
    out.append(text[position:])
    return "".join(out)


# Linear-time tokenizer for http(s) URLs that were only partly percent-encoded
# (for example ``%23`` for ``#``); decoding is bounded in _redact_encoded_http_url.
_HTTP_URL_TOKEN = re.compile(r"(?i)(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://[^\s<>\"']+")
# Generic names (key, code, sig, sid) are sensitive in URL query/fragment context
# only. Assignment, mapping, flag and XML checks use the shared credential nouns.
_QUERY_GENERIC_ALTERNATION = "|".join(sorted(map(re.escape, _QUERY_ONLY_GENERIC_NAMES)))
_CREDENTIAL_QUERY = re.compile(
    r"(?i)([?&;](?:"
    + _credential_alternation()
    + r"|"
    + _QUERY_GENERIC_ALTERNATION
    + r")=)([^&#;\s]+)"
)
# A fragment ends at whitespace or a delimiter that closes a quoted/bracketed
# context, so surrounding JSON, Markdown and prose survive redaction.
# Earlier passes may already have inserted the ``[REDACTED]`` marker, so it is
# consumed as one unit rather than ending the fragment at its closing bracket.
_URL_SCHEME = re.compile(r"(?i)[a-z][a-z0-9+.-]*://")
# ``#state=1,code=SECRET``: a comma directly followed by ``key=`` continues the fragment.
_FRAGMENT_PAIR_AFTER_COMMA = re.compile(r"[A-Za-z0-9_.-]+=")
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
        if char == "," and _FRAGMENT_PAIR_AFTER_COMMA.match(raw, index + 1):
            index += 1
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
_ENCODED_HTTP_URL = re.compile(
    r"(?i)(?<![a-z0-9+.-])[a-z](?:[a-z0-9.-]|\+|%(?:25)*2b)*"
    r"%(?:25)*3a%(?:25)*2f%(?:25)*2f[^\s<>\"']+"
)
# Percent-encoded credential *keys* in URL queries are not matched by the
# plain-text assignment pattern. Decode only the key and retain the URL shape.
# Match raw punctuation in keys (api[key], api+key, api/key) as well as
# percent-encoded spelling. Treat legacy semicolons as query separators,
# including when an earlier non-sensitive parameter precedes the secret.
# The shared key classifier decides sensitivity.
_ENCODED_CREDENTIAL_QUERY = re.compile(r"(?i)([?&;])([^?&#=;\s]+)(=)([^&#;\s]+)")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD_SPLIT = re.compile(r"[^A-Za-z0-9]+")


def _key_words(key: object) -> tuple[str, ...]:
    raw = str(key)
    # Normalize case before detecting camel boundaries so irregular casing such
    # as ``SeCrEt`` cannot split a credential noun into unrelated fragments.
    separated = _CAMEL_BOUNDARY.sub("_", raw.lower())
    return tuple(part.lower() for part in _WORD_SPLIT.split(separated) if part)


def _is_secret_key(key: object) -> bool:
    words = _key_words(key)
    if not words:
        return False
    final_word = words[-1]
    if final_word in _CREDENTIAL_NOUNS or any(
        final_word.endswith(noun) for noun in _CREDENTIAL_SUFFIXES
    ):
        return True
    return len(words) > 1 and words[-2:] in _CREDENTIAL_PAIRS


def _redact_assignment(match: re.Match[str]) -> str:
    if not _is_secret_key(match.group(1)):
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}[REDACTED]"


def _redact_quoted_mapping_open(match: re.Match[str]) -> str:
    if not _is_secret_key(match.group(2)):
        return match.group(0)
    key = f"{match.group(1)}{match.group(2)}{match.group(1)}"
    return f"{key}{match.group(3)}{match.group(4)}[REDACTED]"


def _redact_quoted_mapping_assignment(match: re.Match[str]) -> str:
    if not _is_secret_key(match.group(2)):
        return match.group(0)
    return (
        f"{match.group(1)}{match.group(2)}{match.group(1)}"
        f"{match.group(3)}{match.group(4)}[REDACTED]{match.group(4)}"
    )


def _redact_tuple_pair(match: re.Match[str]) -> str:
    if not _is_secret_key(match.group(3)):
        return match.group(0)
    quote = match.group(2)
    head = f"{match.group(1)}{quote}{match.group(3)}{quote}{match.group(4)}"
    return f"{head}{match.group(5)}[REDACTED]{match.group(5)}"


def _is_secret_name(name: str) -> bool:
    """A flag or element name that *is* a credential (``--api-key``, ``<password>``).

    ``--token-count`` and ``<password-policy>`` mention a credential word but name
    something else, so the last word must be the credential noun. A one-letter
    ``-p`` stays benign; longer names follow credential nouns.

    Query-only generic names are documented in the constants above and do not
    broaden assignment or flag matching.
    """

    words = _key_words(name)
    if not words:
        return False
    # ``key`` is generic in assignments and URLs, but a key-named CLI option
    # explicitly asks for a key value and is therefore treated as sensitive.
    ends_in_pair = len(words) > 1 and words[-2:] in _CREDENTIAL_PAIRS
    return (words[-1] in _CREDENTIAL_NOUNS or words[-1] == "key" or ends_in_pair) and (
        _is_secret_key(name) or words == ("key",)
    )


def _redact_cli_flag(match: re.Match[str]) -> str:
    if not _is_secret_name(match.group(1)):
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}[REDACTED]"


def _redact_xml_element(match: re.Match[str]) -> str:
    if not _is_secret_name(match.group(2)):
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]{match.group(5)}"


def _redact_quoted_value_assignment(match: re.Match[str]) -> str:
    if not _is_secret_key(match.group(1)):
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}[REDACTED]"


def _redact_escaped_quote_pair(match: re.Match[str]) -> str:
    if not _is_secret_key(match.group(2)):
        return match.group(0)
    quote = match.group(1)
    return (
        f"{quote}{match.group(2)}{quote}{match.group(3)}{match.group(4)}[REDACTED]{match.group(6)}"
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
        keys = [part.partition("=")[0] for part in re.split(r"[&;,]", fragment) if "=" in part]
        if any(key.lower() in _QUERY_ONLY_GENERIC_NAMES or _is_secret_key(key) for key in keys):
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
        # ``unquote_plus`` turns the "+" of a scheme such as ``git+ssh`` into a space.
        decoded = original
        for _ in range(_MAX_DECODE_LAYERS):
            step = unquote(decoded)
            if step == decoded:
                break
            decoded = step
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
        layer.lower() in _QUERY_ONLY_GENERIC_NAMES or _is_secret_key(layer)
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


def _drop_cut_url_tail(kept: str) -> str:
    """Hide a URL token cut off by the length cap.

    A password cut before its ``@`` has no delimiter left to recognise it by, so
    the unfinished last token is dropped when it starts a URL with ``user:`` text.
    """

    marker = kept.rfind("://")
    if marker == -1:
        return kept
    tail = kept[marker + 3 :]
    if re.search(r"[\s\"'<>@]", tail) is not None or ":" not in tail:
        return kept
    return kept[: marker + 3] + "[REDACTED]"


def _redact_text(value: str) -> str:
    """Apply every redaction pass in a fixed order.

    Order matters: quoted containers and auth headers first (they own their
    quotes), then URL fragments (before the greedy generic assignment pass),
    then assignments, plain and encoded credential queries, URL userinfo, and
    finally encoded/partly-encoded http(s) tokens, which re-enter this function.
    """

    if len(value) > MAX_REDACTED_TEXT_CHARS:
        value = _drop_cut_url_tail(value[:MAX_REDACTED_TEXT_CHARS]) + _TRUNCATION_MARKER
    value = _PEM_PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
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
    value = _QUOTED_MAPPING_OPEN.sub(_redact_quoted_mapping_open, value)
    value = _ESCAPED_QUOTE_PAIR.sub(_redact_escaped_quote_pair, value)
    value = _TUPLE_PAIR.sub(_redact_tuple_pair, value)
    value = _XML_ELEMENT.sub(_redact_xml_element, value)
    value = _CLI_FLAG_VALUE.sub(_redact_cli_flag, value)
    value = _QUOTED_VALUE_ASSIGNMENT.sub(_redact_quoted_value_assignment, value)
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
        if len(value) == 2 and isinstance(value[0], (str, bytes)):
            key = (
                value[0].decode("utf-8", errors="replace")
                if isinstance(value[0], bytes)
                else value[0]
            )
            if _is_secret_key(key):
                return [redact(value[0]), "[REDACTED]"]
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
