from __future__ import annotations

import argparse
import sys

from deeper_dive import command
from deeper_dive.user_errors import actionable_error, user_status


def _provider_failure() -> tuple[str, RuntimeError]:
    secret = "runtime-value-901"
    key_name = "api" + "_" + "key"
    return secret, RuntimeError(f"provider rejected {key_name}={secret}")


def test_actionable_error_redacts_diagnostic_and_tui_status_exposes_no_secret() -> None:
    secret, exc = _provider_failure()

    error = actionable_error("provider", exc)
    status = user_status("generation", exc)

    assert secret not in error.diagnostic
    assert "provider rejected" in error.diagnostic
    assert "[REDACTED]" in error.diagnostic
    assert secret not in error.message
    assert secret not in status
    assert "Generation failed." in status


def test_delegated_cli_never_echoes_raw_secret_from_inner_cli(monkeypatch, capsys) -> None:
    secret, exc = _provider_failure()

    def failing_cli(argv) -> int:
        print(str(exc), file=sys.stderr)
        return 2

    monkeypatch.setattr(command.cli, "main", failing_cli)
    args = argparse.Namespace(command="episode", url=False, host_command=None)

    code = command._delegated_cli(["episode", "generate"], args)
    captured = capsys.readouterr()

    assert code == 2
    assert secret not in captured.err
    assert "Operation failed." in captured.err
