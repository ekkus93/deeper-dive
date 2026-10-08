"""Goal-first generation progress facade over the production monitor controller."""

from __future__ import annotations

from deeper_dive.diagnostics import redact
from deeper_dive.domain.clock import parse_timestamp
from deeper_dive.generation_monitor import GenerationMonitorScreen
from textual.widgets import Button, Static


class GuidedGenerationMonitorScreen(GenerationMonitorScreen):
    """Reuse the durable monitor and runner, with guided cancellation safeguards."""

    def __init__(self) -> None:
        super().__init__()
        self._cancel_confirmation_pending = False

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#screen-title", Static).update("Generating Your Deep Dive")
        self.set_interval(1.0, self.refresh_monitor)

    def on_screen_resume(self) -> None:
        self.refresh_monitor()

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
        self.query_one('Button[name="resume-generation"]', Button).disabled = run.state != "paused"
        self.query_one('Button[name="pause-generation"]', Button).disabled = run.state not in {
            "running",
            "pending",
        }
        self.query_one('Button[name="cancel-generation"]', Button).disabled = run.state in {
            "completed",
            "failed",
            "cancelled",
        }
