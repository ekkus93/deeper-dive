"""Guided project creation."""

from textual.widget import Widget
from textual.widgets import Button, Input, Select, Static

from deeper_dive.wizard_shell_variants import NewDeepDiveWizardShell

PROJECT_AUDIENCE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("General audience", "general"),
    ("Technical audience", "technical"),
    ("Expert audience", "expert"),
)


class GuidedProjectWizard(NewDeepDiveWizardShell):
    # True when the loaded project stores no audience (see ``_show_stored_choice``).
    _project_audience_unset = False

    def step_controls(self) -> tuple[Widget, ...]:
        return (
            Input(placeholder="Project name", id="guided-project-name"),
            Static("", id="guided-project-name-error", markup=False),
            Input(placeholder="Main curiosity prompt", id="guided-project-topic"),
            Static("", id="guided-project-topic-error", markup=False),
            Select(
                list(PROJECT_AUDIENCE_OPTIONS),
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

    def _sync_project_button(self) -> None:
        """The button creates the project once, then saves edits to the same project."""

        label = "Create Project" if self.context.project_id is None else "Save Project"
        self.query_one("#guided-project-create", Button).label = label

    def _mounted(self) -> None:
        super()._mounted()
        self._sync_project_button()

    def _before_mount(self) -> None:
        # Resuming (or remounting) with an existing project must show that
        # project's durable values, not blank controls that Save would then
        # write back over the project.
        self._load_project_form()
        super()._before_mount()

    def _load_project_form(self) -> None:
        project_id = self.context.project_id
        if project_id is None:
            self._project_audience_unset = False
            self._show_stored_choice(
                "#guided-project-audience", PROJECT_AUDIENCE_OPTIONS, "general"
            )
            return
        try:
            project = self.context.composition.service.open_project(project_id)
        except (OSError, KeyError, RuntimeError, ValueError):
            return
        if project is None:
            return
        topic = audience = description = ""
        for line in project.instructions.splitlines():
            label, _, value = line.partition(":")
            value = value.strip()
            if label == "Main curiosity":
                topic = value
            elif label == "Audience":
                audience = value
            elif label == "Description":
                description = value
        self.query_one("#guided-project-name", Input).value = project.name
        self.query_one("#guided-project-topic", Input).value = topic
        self.query_one("#guided-project-description", Input).value = description
        self._project_audience_unset = audience == ""
        self._show_stored_choice("#guided-project-audience", PROJECT_AUDIENCE_OPTIONS, audience)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.name == "create-project":
            event.stop()
            self.action_create_project()
        # Textual dispatches the base-class handlers itself; no super() call.

    def action_create_project(self) -> bool:
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
                if not isinstance(audience_value, str)
                or not (audience or self._project_audience_unset)
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
            return False
        instructions = "\n".join(
            (
                f"Main curiosity: {topic}",
                f"Audience: {audience}",
                *(("Description: " + description,) if description else ()),
            )
        )
        existing_project_id = self.context.project_id
        try:
            if existing_project_id is None:
                project = self.context.composition.service.create_project(
                    name,
                    instructions=instructions,
                )
            else:
                # Edits after creation persist through the production project service.
                project = self.context.composition.service.update_project(
                    existing_project_id, name, instructions=instructions
                )
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_error(
                "Project creation failed."
                if existing_project_id is None
                else "Project update failed.",
                exc,
            )
            return False
        self.query_one("#guided-project-validation", Static).update("")
        for field in ("name", "topic", "audience"):
            self.query_one(f"#guided-project-{field}-error", Static).update("")
        self.context.project_id = project.id
        self._sync_project_button()
        self._sync_text()
        self._remember_current_form()
        self.set_status(
            f"Created project {project.name}. Continue to Sources."
            if existing_project_id is None
            else f"Updated project {project.name}. Continue to Sources."
        )
        return True

    def on_save_exit(self) -> None:
        self.app.push_screen("home")
