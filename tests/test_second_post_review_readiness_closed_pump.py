"""A closed Textual message pump may raise instead of returning False."""

from __future__ import annotations

from typing import cast

from textual.message import Message

from deeper_dive.guided_async_readiness import FirstRunReadinessCoordinator
from deeper_dive.guided_workflow import WizardContext


class RaisingApp:
    def post_message(self, message: Message) -> bool:
        raise RuntimeError("closed message pump")


def test_readiness_dispatch_treats_closed_pump_exception_as_rejection() -> None:
    coordinator = FirstRunReadinessCoordinator(
        cast(WizardContext, object()),
        fingerprint=lambda: "test",
    )
    try:
        assert not coordinator._dispatch(RaisingApp(), lambda: None)
    finally:
        coordinator.close()
