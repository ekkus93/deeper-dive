"""Reusable filesystem fault injection for durable-write failure tests."""

from __future__ import annotations

import errno
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def failing_replace(under: Path, *, code: int = errno.ENOSPC) -> Iterator[list[tuple[str, str]]]:
    """Make ``os.replace`` fail for destinations below ``under``.

    Yields the list of refused ``(source, destination)`` pairs so tests can assert
    the failure was actually exercised. Other paths use the real ``os.replace``.
    """

    real: Callable[..., None] = os.replace
    root = under.resolve()
    refused: list[tuple[str, str]] = []

    def replace(src: str | os.PathLike[str], dst: str | os.PathLike[str], *a: object, **k: object):
        target = Path(dst).resolve()
        if target == root or root in target.parents:
            refused.append((os.fspath(src), os.fspath(dst)))
            raise OSError(code, os.strerror(code))
        return real(src, dst, *a, **k)

    os.replace = replace  # type: ignore[assignment]
    try:
        yield refused
    finally:
        os.replace = real  # type: ignore[assignment]
