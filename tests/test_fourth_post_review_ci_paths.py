"""Every test file named in the CI workflow must exist (FPR-100).

``scripts/check.sh`` does not run the ``fresh-machine`` job, so a renamed or
deleted test file referenced there would only fail on GitHub.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def test_workflows_exist() -> None:
    assert WORKFLOWS


def test_every_test_path_named_in_workflows_exists() -> None:
    missing: list[str] = []
    for workflow in WORKFLOWS:
        for name in re.findall(r"tests/[A-Za-z0-9_./-]+\.py", workflow.read_text()):
            if not (ROOT / name).is_file():
                missing.append(f"{workflow.name}: {name}")
    assert not missing, missing


def _missing_node_ids(text: str, label: str) -> list[str]:
    import ast

    missing: list[str] = []
    for path, name in re.findall(r"(tests/[A-Za-z0-9_./-]+\.py)::([A-Za-z0-9_]+)", text):
        source = ROOT / path
        if not source.is_file():
            continue  # reported by the path test
        defined = {
            node.name
            for node in ast.walk(ast.parse(source.read_text()))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if name not in defined:
            missing.append(f"{label}: {path}::{name}")
    return missing


def test_every_test_node_id_named_in_workflows_exists() -> None:
    """5PR-11: ``tests/x.py::test_name`` must name a function that still exists."""

    missing = [
        m for workflow in WORKFLOWS for m in _missing_node_ids(workflow.read_text(), workflow.name)
    ]
    assert not missing, missing


def test_node_id_check_catches_a_renamed_function() -> None:
    assert _missing_node_ids("run tests/test_cli.py::test_function_that_was_renamed", "x") == [
        "x: tests/test_cli.py::test_function_that_was_renamed"
    ]
    assert (
        _missing_node_ids("run tests/test_cli.py::test_cli_visible_errors_are_sanitized", "x") == []
    )
