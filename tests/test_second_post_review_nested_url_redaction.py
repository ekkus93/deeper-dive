from urllib.parse import quote

from deeper_dive.diagnostics import redact


def test_nested_url_query_redaction() -> None:
    message = "https://outer.test?next=https%3A%2F%2Finner.test%2F%3Fapi_key%3Dtest-canary"
    assert "test-canary" not in str(redact(message))
    assert "next=[REDACTED]" in str(redact(message))


def test_doubly_encoded_nested_url_query_redaction() -> None:
    nested = quote("https://inner.test/?api_key=double-canary", safe="")
    message = f"https://outer.test?next={quote(nested, safe='')}&trace=ok"
    safe = str(redact(message))
    assert "double-canary" not in safe
    assert "next=[REDACTED]" in safe
    assert "trace=ok" in safe


def test_benign_nested_url_remains_unchanged() -> None:
    nested = quote("https://inner.test/docs?section=overview", safe="")
    message = f"https://outer.test?next={nested}&trace=ok"
    assert redact(message) == message
