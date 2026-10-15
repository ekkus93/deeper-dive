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


def _defined(body: list, parts: list[str]) -> bool:  # type: ignore[type-arg]
    """Whether ``parts`` (``Class`` then ``method`` ids, or one function) resolve in ``body``."""

    import ast

    head, rest = parts[0], parts[1:]
    for node in body:
        if rest:
            if isinstance(node, ast.ClassDef) and node.name == head and _defined(node.body, rest):
                return True
        elif (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == head
        ):
            return True
    return False


def _missing_node_ids(text: str, label: str) -> list[str]:
    import ast

    missing: list[str] = []
    for path, name in re.findall(
        r"(tests/[A-Za-z0-9_./-]+\.py)::([A-Za-z0-9_]+(?:::[A-Za-z0-9_]+)*)", text
    ):
        source = ROOT / path
        if not source.is_file():
            continue  # reported by the path test
        if not _defined(ast.parse(source.read_text()).body, name.split("::")):
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


def test_node_id_check_resolves_class_methods() -> None:
    ok = "tests/test_fourth_post_review_ci_paths.py::test_workflows_exist"
    assert _missing_node_ids(ok, "x") == []
    # A ``Class::method`` id resolves through the class body.
    assert _missing_node_ids("tests/test_wizard_shell.py::NoSuchClass::test_x", "x") == [
        "x: tests/test_wizard_shell.py::NoSuchClass::test_x"
    ]
