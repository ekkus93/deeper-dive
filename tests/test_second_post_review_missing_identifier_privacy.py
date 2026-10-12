"""Missing-record diagnostics must not disclose untrusted caller identifiers."""

from __future__ import annotations

from pathlib import Path

import pytest


CANARY = "private-caller-identifier-CANARY-987654321"


@pytest.mark.parametrize(
    "command",
    [
        ["project", "info", CANARY],
        ["source", "list", CANARY],
        ["research", "gaps", CANARY],
        ["host", "list", CANARY],
        ["episode", "list", CANARY],
    ],
)
def test_missing_project_does_not_echo_untrusted_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    from deeper_dive.cli import main

    assert main(["--data-dir", str(tmp_path), *command]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "project not found" in captured.err
    assert CANARY not in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["source", "show"], "source not found"),
        (["host", "edit"], "host not found"),
        (["episode", "show"], "episode not found"),
    ],
)
def test_missing_child_record_does_not_echo_untrusted_id(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
    expected: str,
) -> None:
    import json

    from deeper_dive.cli import main

    assert main(["--data-dir", str(tmp_path), "--json", "project", "create", "Demo"]) == 0
    project_id = str(json.loads(capsys.readouterr().out)["id"])
    assert main(["--data-dir", str(tmp_path), *command, project_id, CANARY]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert expected in captured.err
    assert CANARY not in captured.err
    assert "Traceback" not in captured.err


def test_missing_generation_run_has_stable_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from deeper_dive.cli import main

    assert main(["--data-dir", str(tmp_path), "--json", "project", "create", "Demo"]) == 0
    project_id = str(json.loads(capsys.readouterr().out)["id"])
    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "--json",
                "episode",
                "create",
                project_id,
                "--title",
                "Episode",
            ]
        )
        == 0
    )
    episode_id = str(json.loads(capsys.readouterr().out)["id"])
    assert main(["--data-dir", str(tmp_path), "episode", "pause", project_id, episode_id]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no generation run for episode" in captured.err
    assert episode_id not in captured.err


@pytest.mark.parametrize("method", ["edit", "load_configuration"])
def test_episode_service_missing_record_never_echoes_id(tmp_path: Path, method: str) -> None:
    from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
    from deeper_dive.storage.database import Database

    service = EpisodeConfigurationService(Database(tmp_path / "project.db"))
    with pytest.raises(KeyError, match="episode not found") as exc:
        if method == "edit":
            service.edit(CANARY, EpisodeConfiguration(title="Demo"))
        else:
            service.load_configuration(CANARY)
    assert CANARY not in str(exc.value)
