from __future__ import annotations

from deeper_dive.user_errors import actionable_error, user_status


def test_actionable_error_keeps_status_concise_and_diagnostics_separate() -> None:
    error = actionable_error("provider", RuntimeError("low-level provider detail"))

    assert error.message == (
        "Provider request failed. Check provider health, credentials, model, and network settings."
    )
    assert "low-level provider detail" not in error.message
    assert error.diagnostic == "low-level provider detail"
    assert user_status("provider", RuntimeError("different detail")) == error.message


def test_unknown_area_uses_generic_operation_guidance() -> None:
    error = actionable_error("unknown", ValueError("bad input"))

    assert error.summary == "Operation failed."
    assert "retry" in error.action
    assert error.diagnostic == "bad input"
