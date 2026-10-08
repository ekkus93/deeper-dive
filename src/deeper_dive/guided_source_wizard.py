"""Guided source import and research-policy steps."""

from textual.widget import Widget
from textual.widgets import Button, Input, Select

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.guided_new_deep_dive import GuidedProjectWizard
from deeper_dive.research_policy import ResearchMode, ResearchPolicy


class GuidedSourceWizard(GuidedProjectWizard):
    def step_controls(self) -> tuple[Widget, ...]:
        return (
            *super().step_controls(),
            Input(placeholder="Title", id="guided-source-title"),
            Input(placeholder="Source text", id="guided-source-text"),
            Button("Add Source", name="add-source"),
            Select(
                [
                    ("Use only my sources — no external research", ResearchMode.OFF.value),
                    ("Fill important gaps — may access the network", ResearchMode.USEFUL.value),
                    (
                        "Research extensively — may access the network",
                        ResearchMode.AGGRESSIVE.value,
                    ),
                ],
                value=ResearchMode.USEFUL.value,
                allow_blank=False,
                id="guided-research-policy",
            ),
            Button("Save Research Choice", id="guided-research-save", name="save-research"),
        )

    def step_content(self, step_key: str) -> str:
        if step_key == "research":
            return (
                "Choose how much supplemental research to perform. "
                "Use only my sources keeps automated external searches disabled. "
                "Fill important gaps and Research extensively can contact external "
                "services when the configured network policy permits it. "
                "The production research policy remains authoritative."
            )
        return super().step_content(step_key)

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
        if event.button.name == "save-research":
            event.stop()
            self.action_save_research()
            return
        if event.button.name != "add-source":
            super().on_button_pressed(event)
            return
        event.stop()
        title = self.query_one("#guided-source-title", Input).value.strip()
        body = self.query_one("#guided-source-text", Input).value.strip()
        if not self.context.project_id or not title or not body:
            self.set_status("Project, source title and text required.")
            return
        try:
            self.context.composition.service.add_pasted_source(self.context.project_id, title, body)
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_status(f"Source import failed: {sanitize_exception_message(exc)}")
            return
        self._sync_text()
        self.set_status(f"Imported {title}.")

    def action_save_research(self) -> None:
        project_id = self.context.project_id
        if project_id is None:
            self.set_status("Create a project before choosing research settings.")
            return
        value = self.query_one("#guided-research-policy", Select).value
        try:
            mode = ResearchMode(str(value))
            project = self.context.composition.service.open_project(project_id)
            if project is None:
                raise ValueError("Project is no longer available.")
            self.context.composition.research_controller.save_policy(
                project_id, ResearchPolicy(mode=mode), project.instructions or ""
            )
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_status(f"Research policy save failed: {sanitize_exception_message(exc)}")
            return
        self._sync_text()
        self.set_status(f"Saved research choice: {mode.value}.")

    def _toggle(self) -> None:
        step = self.context.state.current_step
        for suffix in ("name", "topic", "create"):
            self.query_one(f"#guided-project-{suffix}").display = step == "project"
        for suffix in ("title", "text"):
            self.query_one(f"#guided-source-{suffix}").display = step == "sources"
        for button in self.query(Button):
            if button.name == "add-source":
                button.display = step == "sources"
        self.query_one("#guided-research-policy", Select).display = step == "research"
        self.query_one("#guided-research-save", Button).display = step == "research"
