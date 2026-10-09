"""Reusable confirmation state never deletes without explicit target-matched consent."""

from __future__ import annotations

import pytest

from deeper_dive.destructive_confirmation import DestructiveConfirmation


def test_single_use_confirmation_rejects_implicit_and_stale_actions() -> None:
    confirmation = DestructiveConfirmation()
    assert not confirmation.consume("host-one")
    confirmation.request("host-one")
    assert not confirmation.consume("host-two")
    assert not confirmation.consume("host-one")
    confirmation.request("host-one")
    assert confirmation.consume("host-one")
    assert not confirmation.consume("host-one")


def test_cancel_and_rearm_are_non_destructive() -> None:
    confirmation = DestructiveConfirmation()
    confirmation.request("source-A")
    confirmation.cancel()
    assert not confirmation.consume("source-A")
    confirmation.request("source-A")
    confirmation.request("source-B")
    assert not confirmation.consume("source-A")
    assert not confirmation.consume("source-B")
    confirmation.request("source-B")
    assert confirmation.consume("source-B")


def test_empty_target_cannot_be_armed() -> None:
    with pytest.raises(ValueError, match="target is required"):
        DestructiveConfirmation().request("")
