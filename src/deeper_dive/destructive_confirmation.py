"""Single-use, target-bound destructive action confirmation state."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DestructiveConfirmation:
    """A request arms a target; only an explicit confirmation can consume it."""

    target: str | None = None

    def request(self, target: str) -> None:
        if not target:
            raise ValueError("confirmation target is required")
        self.target = target

    def consume(self, current_target: str) -> bool:
        accepted = self.target is not None and self.target == current_target
        self.target = None
        return accepted

    def cancel(self) -> None:
        self.target = None
