"""Reusable confirmation prevents accidental or repeated destructive actions."""

from __future__ import annotations

from deeper_dive.destructive_confirmation import PendingRemoval


def test_confirmation_requires_exact_identity_and_is_one_shot() -> None:
    confirm = PendingRemoval()
    assert not confirm.consume("p:one")
    confirm.request("p:one")
    assert not confirm.consume("p:other")
    assert not confirm.consume("p:one")
    confirm.request("p:one")
    assert confirm.consume("p:one")
    assert not confirm.consume("p:one")


def test_confirmation_cancel_is_non_destructive_and_repeat_safe() -> None:
    confirm = PendingRemoval()
    confirm.request("provider")
    assert confirm.cancel()
    assert not confirm.cancel()
    assert not confirm.consume("provider")
