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
