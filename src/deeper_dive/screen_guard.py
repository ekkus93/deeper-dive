"""Keep recoverable service errors from terminating the legacy Textual screens."""

from __future__ import annotations

import functools
import sqlite3
from collections.abc import Callable
from typing import Any, TypeVar

from deeper_dive.diagnostics import sanitize_exception_message

# Everything a storage/planner/config/run call can raise for a recoverable reason.
# Typed episode errors subclass ValueError.
SERVICE_ERRORS: tuple[type[BaseException], ...] = (
    KeyError,
    IndexError,
    OSError,
    RuntimeError,
    ValueError,
    sqlite3.Error,
)

F = TypeVar("F", bound=Callable[..., Any])


def report_service_errors(label: str) -> Callable[[F], F]:
    """Report ``SERVICE_ERRORS`` from a screen action as a sanitized status line.

    The screen must expose ``_status(str)`` or ``_set_status(str)``. Durable state
    is whatever the failed service call left (services commit or roll back
    atomically); the screen simply stays alive and tells the user.
    """

    def decorator(function: F) -> F:
        @functools.wraps(function)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return function(self, *args, **kwargs)
            except SERVICE_ERRORS as exc:
                report = getattr(self, "_status", None) or self._set_status
                report(f"{label}: {sanitize_exception_message(exc)}")
                return None

        return wrapper  # type: ignore[return-value]

    return decorator
