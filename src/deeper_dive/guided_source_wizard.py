"""Guided source step."""

from textual.widgets import Button, Input

from deeper_dive.guided_new_deep_dive import GuidedProjectWizard


class GuidedSourceWizard(GuidedProjectWizard):
    def step_controls(self) -> tuple[Input | Button, ...]:
        return (
            *super().step_controls(),
            Input(placeholder="Title", id="guided-source-title"),
            Input(placeholder="Source text", id="guided-source-text"),
            Button("Add Source", name="add-source"),
        )

    def on_mount(self) -> None:
        super().on_mount()
        self._toggle()

    def action_continue(self) -> None:
        super().action_continue()
        self._toggle()

    def action_back(self) -> None:
        super().action_back()
        self._toggle()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.name != "add-source":
            super().on_button_pressed(event)
            return
        event.stop()
        title = self.query_one("#guided-source-title", Input).value.strip()
        body = self.query_one("#guided-source-text", Input).value.strip()
        if not self.context.project_id or not title or not body:
            self.set_status("Project, source title and text required.")
            return
        self.context.composition.service.add_pasted_source(self.context.project_id, title, body)
        self._sync_text()
        self.set_status(f"Imported {title}.")

    def _toggle(self) -> None:
        project = self.context.state.current_step == "project"
        for suffix in ("name", "topic", "create"):
            self.query_one(f"#guided-project-{suffix}").display = project
        for suffix in ("title", "text"):
            self.query_one(f"#guided-source-{suffix}").display = not project
