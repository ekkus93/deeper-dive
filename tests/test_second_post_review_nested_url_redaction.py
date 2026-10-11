from deeper_dive.diagnostics import redact


def test_nested_url_query_redaction() -> None:
    message = "https://outer.test?next=https%3A%2F%2Finner.test%2F%3Fapi_key%3Dtest-canary"
    assert "test-canary" not in str(redact(message))
    assert "next=[REDACTED]" in str(redact(message))
