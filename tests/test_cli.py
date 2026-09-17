from __future__ import annotations

import json
from pathlib import Path

from deeper_dive.cli import main


def test_cli_project_create_list_info_json(tmp_path: Path, capsys: object) -> None:
    assert main(["--data-dir", str(tmp_path), "--json", "project", "create", "Demo"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    created = json.loads(captured.out)
    assert created["name"] == "Demo"

    assert main(["--data-dir", str(tmp_path), "--json", "project", "list"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    listed = json.loads(captured.out)
    assert [item["id"] for item in listed] == [created["id"]]

    assert main(
        ["--data-dir", str(tmp_path), "--json", "project", "info", created["id"]]
    ) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.out) == created


def test_cli_missing_project_uses_stderr_and_nonzero(tmp_path: Path, capsys: object) -> None:
    missing = "00000000-0000-0000-0000-000000000001"
    assert main(["--data-dir", str(tmp_path), "project", "info", missing]) == 2
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == ""
    assert "project not found" in captured.err
