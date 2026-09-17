from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive import __version__
from deeper_dive.cli import main


def test_cli_help_exits_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    assert "evidence-grounded deep dives" in capsys.readouterr().out


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_cli_project_create_list_info_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--data-dir", str(tmp_path), "--json", "project", "create", "Demo"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["name"] == "Demo"

    assert main(["--data-dir", str(tmp_path), "--json", "project", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in listed] == [created["id"]]

    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--json",
                "project",
                "info",
                created["id"],
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == created


def test_cli_missing_project_uses_stderr_and_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = "00000000-0000-0000-0000-000000000001"
    assert main(["--data-dir", str(tmp_path), "project", "info", missing]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "project not found" in captured.err
