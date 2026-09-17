"""Client-neutral progress events for long-running application use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    operation: str
    state: str
    message: str = ""
    completed: int | None = None
    total: int | None = None


class ProgressSink(Protocol):
    def __call__(self, event: ProgressEvent) -> None: ...
