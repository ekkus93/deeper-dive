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


def _create_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert (
        main(["--data-dir", str(tmp_path), "--json", "project", "create", "Demo"])
        == 0
    )
    return json.loads(capsys.readouterr().out)


def test_cli_project_create_list_info_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    created = _create_project(tmp_path, capsys)
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
                str(created["id"]),
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


def test_cli_source_file_directory_lifecycle_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _create_project(tmp_path, capsys)
    project_id = str(project["id"])
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "alpha.txt").write_text("alpha evidence", encoding="utf-8")
    (corpus / "beta.md").write_text("# Beta\n\nbeta evidence", encoding="utf-8")

    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--json",
                "source",
                "add",
                project_id,
                str(corpus),
            ]
        )
        == 0
    )
    added = json.loads(capsys.readouterr().out)
    assert len(added["imported"]) == 2
    assert {item["disposition"] for item in added["candidates"]} == {"import"}

    assert (
        main(["--data-dir", str(tmp_path), "--json", "source", "list", project_id])
        == 0
    )
    sources = json.loads(capsys.readouterr().out)
    assert len(sources) == 2
    source_id = sources[0]["id"]

    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--json",
                "source",
                "show",
                project_id,
                source_id,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["id"] == source_id

    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--json",
                "source",
                "exclude",
                project_id,
                source_id,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["included"] is False
    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--json",
                "source",
                "include",
                project_id,
                source_id,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["included"] is True

    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--json",
                "source",
                "remove",
                project_id,
                source_id,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"id": source_id, "removed": True}


def test_cli_source_add_url_is_supported_without_network_in_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["source", "add", "--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--url" in output
    assert "HTTP/HTTPS" in output
