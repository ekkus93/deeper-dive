"""Guided project creation."""

from textual.widget import Widget
from textual.widgets import Button, Input, Select

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.wizard_shell import NewDeepDiveWizardShell


class GuidedProjectWizard(NewDeepDiveWizardShell):
    def step_controls(self) -> tuple[Widget, ...]:
        return (
            Input(placeholder="Project name", id="guided-project-name"),
            Input(placeholder="Main curiosity prompt", id="guided-project-topic"),
            Select(
                [
                    ("General audience", "general"),
                    ("Technical audience", "technical"),
                    ("Expert audience", "expert"),
                ],
                value="general",
                allow_blank=False,
                id="guided-project-audience",
            ),
            Input(
                placeholder="Optional project description",
                id="guided-project-description",
            ),
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
        audience_value = self.query_one("#guided-project-audience", Select).value
        audience = str(audience_value).strip()
        description = self.query_one("#guided-project-description", Input).value.strip()
        if not name or not topic or audience not in {"general", "technical", "expert"}:
            self.set_status("Project name, curiosity prompt, and audience are required.")
            return
        if self.context.project_id is not None:
            self.set_status("Project already created.")
            return
        instructions = "\n".join(
            (
                f"Main curiosity: {topic}",
                f"Audience: {audience}",
                *(("Description: " + description,) if description else ()),
            )
        )
        try:
            project = self.context.composition.service.create_project(
                name,
                instructions=instructions,
            )
        except (OSError, KeyError, ValueError) as exc:
            self.set_status(sanitize_exception_message(exc))
            return
        self.context.project_id = project.id
        self._sync_text()
        self.set_status(f"Created project {project.name}. Continue to Sources.")

    def on_save_exit(self) -> None:
        self.app.push_screen("home")
