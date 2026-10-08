"""Goal-first generation progress facade over the production monitor controller."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Button, Static

from deeper_dive.diagnostics import redact
from deeper_dive.domain.clock import parse_timestamp
from deeper_dive.generation_monitor import GenerationMonitorScreen

_STAGE_REPAIR_ROUTES = {
    "sources": "sources",
    "research": "research",
    "planning": "episode",
    "conversation": "providers",
    "verification": "providers",
    "tts": "providers",
    "composition": "providers",
    "export": "library",
}


class GuidedGenerationMonitorScreen(GenerationMonitorScreen):
    """Reuse the durable monitor and runner, with guided cancellation safeguards."""

    def __init__(self) -> None:
        super().__init__()
        self._cancel_confirmation_pending = False

    def on_mount(self) -> None:
        self._ensure_repair_action()
        super().on_mount()
        self.query_one("#screen-title", Static).update("Generating Your Deep Dive")
        self.set_interval(1.0, self.refresh_monitor)
        self.call_after_refresh(self._route_completed_run)

    def on_screen_resume(self) -> None:
        self.refresh_monitor()
        self.call_after_refresh(self._route_completed_run)

    def _route_completed_run(self) -> None:
        """Recover the Ready handoff from durable state after reopening a monitor."""
        run = self._run()
        if run is not None and run.state == "completed" and self.app.screen is self:
            self._app.action_navigate("ready")

    async def _background_run(self, run_id: str) -> None:
        await super()._background_run(run_id)
        run = self._run()
        if run is not None and run.id == run_id:
            self._route_completed_run()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.name == "repair-generation":
            event.stop()
            self.action_repair_configuration()
            return
        super().on_button_pressed(event)

    def action_repair_configuration(self) -> None:
        run = self._run()
        if run is None:
            self._status("No generation run is selected.")
            return
        destination = _STAGE_REPAIR_ROUTES.get(run.stage, "providers")
        self._app.action_navigate(destination)

    def action_cancel(self) -> None:
        if not self._cancel_confirmation_pending:
            self._cancel_confirmation_pending = True
            self._status("Cancel this generation run? Choose Cancel again to confirm.")
            return
        self._cancel_confirmation_pending = False
        super().action_cancel()

    def action_pause(self) -> None:
        self._cancel_confirmation_pending = False
        super().action_pause()

    def action_resume(self) -> None:
        self._cancel_confirmation_pending = False
        super().action_resume()

    def refresh_monitor(self, status: str | None = None) -> None:
        super().refresh_monitor(status)
        snapshot = self._app.generation_monitor_controller.snapshot(self._app)
        run = snapshot.run
        if run is None:
            return
        try:
            seconds = max(
                0,
                int(
                    (
                        self._app.service.clock.now() - parse_timestamp(run.created_at)
                    ).total_seconds()
                ),
            )
        except ValueError:
            seconds = 0
        existing = self.query_one("#generation-state", Static)
        existing.update(
            str(redact(f"Run: {run.id} | {run.state} | stage {run.stage} | elapsed {seconds}s"))
        )
        if run.state == "failed":
            self.query_one("#diagnostics-summary", Static).update(
                str(
                    redact(
                        f"Generation failed at stage {run.stage}. "
                        f"Code: {run.failure_code or 'unknown'}. "
                        f"{run.failure_message or 'Inspect diagnostics for details.'}"
                    )
                )
            )
        self._button("resume-generation").disabled = run.state != "paused"
        self._button("pause-generation").disabled = run.state not in {
            "running",
            "pending",
        }
        self._button("cancel-generation").disabled = run.state in {
            "completed",
            "failed",
            "cancelled",
        }
        self._button("repair-generation").disabled = run.state != "failed"

    def _ensure_repair_action(self) -> None:
        if any(button.id == "guided-monitor-repair" for button in self.query(Button)):
            return
        self.query_one("#content", VerticalScroll).mount(
            Button(
                "Repair Configuration",
                id="guided-monitor-repair",
                name="repair-generation",
            ),
            before="#screen-status",
        )

    def _button(self, name: str) -> Button:
        for button in self.query(Button):
            if button.name == name:
                return button
        raise LookupError(name)
