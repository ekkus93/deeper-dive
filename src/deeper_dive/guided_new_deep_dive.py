"""Guided project creation via the shared production service."""

from textual.widgets import Button, Input

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.wizard_shell import NewDeepDiveWizardShell


class GuidedProjectWizard(NewDeepDiveWizardShell):
    def step_controls(self) -> tuple[Input | Button, ...]:
        return (
            Input(placeholder="Project name", id="guided-project-name"),
            Input(placeholder="Main curiosity prompt", id="guided-project-topic"),
            Button("Create Project", id="guided-project-create", name="create-project"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.name == "create-project":
            event.stop()
            self.action_create_project()
        else:
            super().on_button_pressed(event)

    def action_create_project(self) -> None:
        name = self.query_one("#guided-project-name", Input).value.strip()
        topic = self.query_one("#guided-project-topic", Input).value.strip()
        if not name or not topic:
            self.set_status("Project name and curiosity prompt are required.")
            return
        if self.context.project_id is not None:
            self.set_status("Project already created.")
            return
        try:
            project = self.context.composition.service.create_project(name, instructions=topic)
        except (OSError, KeyError, ValueError) as exc:
            self.set_status(sanitize_exception_message(exc))
            return
        self.context.project_id = project.id
        self._sync_text()
        self.set_status(f"Created project {project.name}. Continue to Sources.")
