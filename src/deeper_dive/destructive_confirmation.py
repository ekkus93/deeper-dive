"""Reusable one-shot confirmation guard for destructive TUI mutations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PendingRemoval:
    """Bind an explicit confirmation to one exact selected durable identity."""

    target: str | None = None

    def request(self, identity: str) -> None:
        if not identity:
            raise ValueError("a non-empty target identity is required")
        self.target = identity

    def consume(self, selected: str | None) -> bool:
        """Confirm only the originally selected identity, once."""
        approved = self.target is not None and self.target == selected
        self.target = None
        return approved

    def cancel(self) -> bool:
        was_pending = self.target is not None
        self.target = None
        return was_pending
