"""5PR-09: the advisory lock file is shared by every spelling of the config path."""

from __future__ import annotations

import os
import select
import subprocess
import sys
from pathlib import Path

import pytest

from deeper_dive.user_config import UserConfigError, UserConfigStore

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


def _child_blocks(
    path: Path,
    *,
    child_script: str = _CHILD,
    ready_timeout: float = _IMPORT_SECONDS,
) -> bool:
    """True when a child that finished importing cannot take the lock within 1.5 s.

    The child reports ``ready`` after its imports, so a slow start cannot read as
    contention, and a child that crashes fails the test instead of passing it.
    """

    process = subprocess.Popen(
        [sys.executable, "-c", child_script, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready = _read_line(process, ready_timeout)
        if ready != "ready":
            process.kill()
            process.wait()
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise AssertionError(stderr or f"child did not report ready: {ready!r}")
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


def test_child_without_ready_output_is_killed_before_stderr_read(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="child did not report ready"):
        _child_blocks(
            tmp_path / "config.json",
            child_script="import time; time.sleep(60)",
            ready_timeout=0.05,
        )


def test_dangling_parent_symlink_is_refused_before_creating_its_target(tmp_path: Path) -> None:
    missing_target = tmp_path / "outside-not-created"
    dangling = tmp_path / "dangling-parent"
    dangling.symlink_to(missing_target, target_is_directory=True)
    store = UserConfigStore(dangling / "nested" / "config.json")

    with pytest.raises(UserConfigError, match="invalid user configuration path"):
        store.load()

    assert not missing_target.exists()
