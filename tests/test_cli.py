from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive import __version__
from deeper_dive import cli as cli_module
from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.research_gaps import ResearchGap, ResearchGapCategory


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
    assert main(["--data-dir", str(tmp_path), "--json", "project", "create", "Demo"]) == 0
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


def test_cli_visible_errors_are_sanitized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "cli-runtime-value-321"
    key_name = "api" + "_" + "key"

    def fail_command(service: object, args: object) -> int:
        raise RuntimeError(f"provider failed {key_name}={secret}")

    monkeypatch.setattr(cli_module, "_project_command", fail_command)

    assert main(["--data-dir", str(tmp_path), "project", "list"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert secret not in captured.err
    assert "provider failed" in captured.err
    assert f"{key_name}=[REDACTED]" in captured.err


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

    assert main(["--data-dir", str(tmp_path), "--json", "source", "list", project_id]) == 0
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


def test_cli_research_uses_production_composition_controller(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, capsys)
    project_id = str(project["id"])
    composition = ProductionComposition.build(data_dir=tmp_path)

    class FakeResearchController:
        def __init__(self) -> None:
            self.analyzed: list[tuple[str, str]] = []

        def analyze(self, requested_project_id: str, focus: str) -> tuple[ResearchGap, ...]:
            self.analyzed.append((requested_project_id, focus))
            return (
                ResearchGap(
                    id="gap-from-composition",
                    project_id=requested_project_id,
                    category=ResearchGapCategory.OTHER,
                    rationale="created by composition controller",
                    priority=3,
                ),
            )

    controller = FakeResearchController()
    composition.research_controller = controller  # type: ignore[assignment]
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )

    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--json",
                "research",
                "analyze",
                project_id,
                "--focus",
                "missing context",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["id"] == "gap-from-composition"
    assert controller.analyzed == [(project_id, "missing context")]
