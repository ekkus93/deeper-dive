"""5PR-09: the advisory lock file is shared by every spelling of the config path."""

from __future__ import annotations

import os
import select
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
    "store = UserConfigStore(Path(sys.argv[1]))\n"
    "print('ready', flush=True)\n"
    "handle = store._open_advisory_lock()\n"
    "print('acquired', flush=True)\n"
)
_IMPORT_SECONDS = 60.0
_CONTENTION_SECONDS = 1.5


def _read_line(process: subprocess.Popen[str], timeout: float) -> str | None:
    """The child's next stdout line, or ``None`` if none arrives within ``timeout``."""

    assert process.stdout is not None
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    return process.stdout.readline().strip() if ready else None


def _child_blocks(path: Path) -> bool:
    """True when a child that finished importing cannot take the lock within 1.5 s.

    The child reports ``ready`` after its imports, so a slow start cannot read as
    contention, and a child that crashes fails the test instead of passing it.
    """

    process = subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _read_line(process, _IMPORT_SECONDS) == "ready", (
            process.stderr and process.stderr.read()
        )
        line = _read_line(process, _CONTENTION_SECONDS)
        if line is None:
            return True
        assert line == "acquired", line
        assert process.wait(timeout=10) == 0
        return False
    finally:
        process.kill()
        process.wait()
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()


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
