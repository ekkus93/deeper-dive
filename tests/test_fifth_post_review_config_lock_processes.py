"""5PR-09: the advisory lock file is shared by every spelling of the config path."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from deeper_dive.user_config import UserConfigStore

pytestmark = pytest.mark.skipif(
    not hasattr(os, "symlink") or sys.platform == "win32", reason="needs flock and symlinks"
)

_CHILD = (
    "import sys\n"
    "from pathlib import Path\n"
    "from deeper_dive.user_config import UserConfigStore\n"
    "handle = UserConfigStore(Path(sys.argv[1]))._open_advisory_lock()\n"
    "print('acquired', flush=True)\n"
)


def _child_blocks(path: Path) -> bool:
    try:
        subprocess.run(
            [sys.executable, "-c", _CHILD, str(path)],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return True
    return False


def test_symlinked_directory_spelling_contends_on_the_same_lock_file(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    holder = UserConfigStore(real / "config.json")
    handle = holder._open_advisory_lock()
    assert handle is not None
    try:
        assert _child_blocks(tmp_path / "link" / "config.json")
    finally:
        handle.close()


def test_symlinked_file_spelling_contends_on_the_same_lock_file(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "config.json").write_text("{}")
    (tmp_path / "alias.json").symlink_to(real / "config.json")
    handle = UserConfigStore(real / "config.json")._open_advisory_lock()
    assert handle is not None
    try:
        assert _child_blocks(tmp_path / "alias.json")
    finally:
        handle.close()


def test_an_unrelated_path_does_not_contend(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    handle = UserConfigStore(tmp_path / "a" / "config.json")._open_advisory_lock()
    assert handle is not None
    try:
        assert not _child_blocks(tmp_path / "b" / "config.json")
    finally:
        handle.close()
