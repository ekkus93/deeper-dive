from __future__ import annotations


def test_cli_visible_error_text_uses_canonical_redaction() -> None:
    from deeper_dive.user_errors import actionable_error

    private_value = "visible-value-234"
    key_name = "api" + "_" + "key"
    error = actionable_error(
        "provider",
        RuntimeError(f"provider rejected request with {key_name}={private_value}"),
    )

    assert private_value not in error.message
    assert private_value not in error.diagnostic
    assert f"{key_name}=[REDACTED]" in error.diagnostic
    assert "Provider request failed." in error.message


def test_tui_visible_status_text_uses_canonical_redaction() -> None:
    from deeper_dive.user_errors import user_status

    private_value = "visible-value-567"
    header = "Author" + "ization"
    status = user_status("generation", RuntimeError(f"{header}: Bearer {private_value}"))

    assert private_value not in status
    assert "Generation failed." in status
