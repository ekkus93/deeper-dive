"""Guided project creation."""

from textual.widget import Widget
from textual.widgets import Button, Input, Select, Static

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.wizard_shell import NewDeepDiveWizardShell


class GuidedProjectWizard(NewDeepDiveWizardShell):
    def step_controls(self) -> tuple[Widget, ...]:
        return (
            Input(placeholder="Project name", id="guided-project-name"),
            Static("", id="guided-project-name-error", markup=False),
            Input(placeholder="Main curiosity prompt", id="guided-project-topic"),
            Static("", id="guided-project-topic-error", markup=False),
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
            Static("", id="guided-project-audience-error", markup=False),
            Input(
                placeholder="Optional project description",
                id="guided-project-description",
            ),
            Static("", id="guided-project-validation", markup=False),
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
        field_errors = {
            "name": "Error: Project name is required." if not name else "",
            "topic": "Error: Main curiosity is required." if not topic else "",
            "audience": (
                "Error: Choose a supported audience."
                if audience not in {"general", "technical", "expert"}
                else ""
            ),
        }
        for field, error in field_errors.items():
            self.query_one(f"#guided-project-{field}-error", Static).update(error)
        if any(field_errors.values()):
            self.query_one("#guided-project-validation", Static).update(
                " ".join(error for error in field_errors.values() if error)
            )
            self.set_status("Project setup needs attention; no project was created.")
            for field in ("name", "topic", "audience"):
                if field_errors[field]:
                    self.query_one(f"#guided-project-{field}").focus()
                    break
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
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_status(f"Project creation failed: {sanitize_exception_message(exc)}")
            return
        self.query_one("#guided-project-validation", Static).update("")
        for field in ("name", "topic", "audience"):
            self.query_one(f"#guided-project-{field}-error", Static).update("")
        self.context.project_id = project.id
        self._sync_text()
        self.set_status(f"Created project {project.name}. Continue to Sources.")

    def on_save_exit(self) -> None:
        self.app.push_screen("home")
