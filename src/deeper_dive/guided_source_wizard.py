"""Guided source import and research-policy steps."""

from __future__ import annotations

from pathlib import Path

from textual.widget import Widget
from textual.widgets import Button, Input, Select, Static

from deeper_dive.application.service import SourceImportSummary
from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.guided_new_deep_dive import GuidedProjectWizard
from deeper_dive.guided_workflow import CompletionProbe, WizardContext
from deeper_dive.research_policy import ResearchMode, ResearchPolicy
from deeper_dive.storage.repositories import SourceRecord


class GuidedSourceWizard(GuidedProjectWizard):
    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe)
        self._pending_delete_source_id: str | None = None

    def step_controls(self) -> tuple[Widget, ...]:
        return (
            *super().step_controls(),
            Input(placeholder="Pasted source title", id="guided-source-title"),
            Input(placeholder="Paste source text", id="guided-source-text"),
            Button("Add Pasted Text", id="guided-source-add-paste", name="add-source"),
            Input(
                placeholder="File or folder paths, comma separated",
                id="guided-source-paths",
            ),
            Button(
                "Add Files / Folder",
                id="guided-source-add-files",
                name="add-file-sources",
            ),
            Input(
                placeholder="Explicit HTTP/HTTPS URLs, comma separated",
                id="guided-source-urls",
            ),
            Button("Add URLs", id="guided-source-add-urls", name="add-url-sources"),
            Select([], allow_blank=True, id="guided-source-picker"),
            Static("", id="guided-source-summary"),
            Static("", id="guided-source-details"),
            Button(
                "Include / Exclude",
                id="guided-source-toggle",
                name="toggle-source",
            ),
            Button("Delete Source", id="guided-source-delete", name="delete-source"),
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
            Button(
                "Save Research Choice",
                id="guided-research-save",
                name="save-research",
            ),
        )

    def step_content(self, step_key: str) -> str:
        if step_key == "sources":
            return (
                "Add source material through the normal production import paths. "
                "Paste text, choose files or folders, or enter explicit URLs. "
                "Only included sources with parsed/indexed chunks satisfy this step."
            )
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
        self._refresh_sources()
        self._toggle()

    def action_continue(self) -> None:
        super().action_continue()
        self._refresh_sources()
        self._toggle()

    def action_back(self) -> None:
        super().action_back()
        self._refresh_sources()
        self._toggle()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "guided-source-picker":
            self._pending_delete_source_id = None
            self._refresh_source_details()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name or ""
        handlers = {
            "add-source": self.action_add_pasted_source,
            "add-file-sources": self.action_add_file_sources,
            "add-url-sources": self.action_add_url_sources,
            "toggle-source": self.action_toggle_source,
            "delete-source": self.action_delete_source,
            "save-research": self.action_save_research,
        }
        handler = handlers.get(action)
        if handler is not None:
            event.stop()
            handler()
            return
        super().on_button_pressed(event)

    def action_add_pasted_source(self) -> None:
        project_id = self.context.project_id
        title_input = self.query_one("#guided-source-title", Input)
        text_input = self.query_one("#guided-source-text", Input)
        title = title_input.value.strip()
        body = text_input.value.strip()
        if project_id is None or not title or not body:
            self.set_status("Project, source title and text required.")
            return
        try:
            source = self.context.composition.service.add_pasted_source(
                project_id,
                title,
                body,
            )
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_status(f"Source import failed: {sanitize_exception_message(exc)}")
            return
        title_input.value = ""
        text_input.value = ""
        self._refresh_sources(source.id)
        self._sync_text()
        self.set_status(f"Imported {source.title}.")

    def action_add_file_sources(self) -> None:
        project_id = self.context.project_id
        paths_input = self.query_one("#guided-source-paths", Input)
        paths = [Path(value.strip()) for value in paths_input.value.split(",") if value.strip()]
        if project_id is None or not paths:
            self.set_status("Create a project and provide at least one file or folder path.")
            return
        try:
            summary = self.context.composition.service.add_file_sources(project_id, paths)
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_status(f"File/folder import failed: {sanitize_exception_message(exc)}")
            return
        paths_input.value = ""
        preferred = summary.imported[0].id if summary.imported else None
        self._refresh_sources(preferred)
        self._sync_text()
        self.set_status(self._import_summary("file/folder", summary))

    def action_add_url_sources(self) -> None:
        project_id = self.context.project_id
        urls_input = self.query_one("#guided-source-urls", Input)
        urls = [value.strip() for value in urls_input.value.split(",") if value.strip()]
        if project_id is None or not urls:
            self.set_status("Create a project and provide at least one explicit URL.")
            return
        try:
            summary = self.context.composition.service.add_url_sources(project_id, urls)
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_status(f"URL import failed: {sanitize_exception_message(exc)}")
            return
        urls_input.value = ""
        preferred = summary.imported[0].id if summary.imported else None
        self._refresh_sources(preferred)
        self._sync_text()
        self.set_status(self._import_summary("URL", summary))

    def action_toggle_source(self) -> None:
        project_id = self.context.project_id
        source = self._selected_source()
        if project_id is None or source is None:
            self.set_status("Choose a source before changing inclusion.")
            return
        try:
            self.context.composition.service.set_source_included(
                project_id,
                source.id,
                not source.included,
            )
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_status(f"Source update failed: {sanitize_exception_message(exc)}")
            return
        self._pending_delete_source_id = None
        self._refresh_sources(source.id)
        self._sync_text()
        self.set_status(f"{'Included' if not source.included else 'Excluded'} {source.title}.")

    def action_delete_source(self) -> None:
        project_id = self.context.project_id
        source = self._selected_source()
        if project_id is None or source is None:
            self.set_status("Choose a source before deleting.")
            return
        if self._pending_delete_source_id != source.id:
            self._pending_delete_source_id = source.id
            self.set_status(f"Delete {source.title}? Choose Delete Source again to confirm.")
            return
        try:
            self.context.composition.service.delete_source(project_id, source.id)
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_status(f"Source delete failed: {sanitize_exception_message(exc)}")
            return
        self._pending_delete_source_id = None
        self._refresh_sources()
        self._sync_text()
        self.set_status(f"Deleted {source.title}.")

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
                project_id,
                ResearchPolicy(mode=mode),
                project.instructions or "",
            )
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_status(f"Research policy save failed: {sanitize_exception_message(exc)}")
            return
        self._sync_text()
        self.set_status(f"Saved research choice: {mode.value}.")

    def _refresh_sources(self, preferred_source_id: str | None = None) -> None:
        project_id = self.context.project_id
        picker = self.query_one("#guided-source-picker", Select)
        summary = self.query_one("#guided-source-summary", Static)
        if project_id is None:
            picker.set_options([])
            summary.update("Create the project before adding sources.")
            self._refresh_source_details()
            return
        sources = self.context.composition.service.list_sources(project_id)
        picker.set_options(
            [
                (
                    f"{source.title} — {'included' if source.included else 'excluded'} "
                    f"— {source.status} — {source.source_type}",
                    source.id,
                )
                for source in sources
            ]
        )
        ids = {source.id for source in sources}
        if preferred_source_id in ids:
            picker.value = preferred_source_id
        elif sources and (not isinstance(picker.value, str) or picker.value not in ids):
            picker.value = sources[0].id
        if not sources:
            summary.update("No sources yet. Add pasted text, files/folders, or an explicit URL.")
        else:
            rows = [
                (
                    f"{source.title} | {'included' if source.included else 'excluded'} "
                    f"| {source.status} | {source.source_type}"
                )
                for source in sources
            ]
            summary.update("\n".join(rows))
        self._refresh_source_details()

    def _refresh_source_details(self) -> None:
        details = self.query_one("#guided-source-details", Static)
        source = self._selected_source()
        if source is None:
            details.update("No source selected.")
            return
        project_id = self.context.project_id
        chunk_count = (
            len(self.context.composition.service.list_source_chunks(project_id, source.id))
            if project_id is not None
            else 0
        )
        details.update(
            "\n".join(
                (
                    f"Title: {source.title}",
                    f"Status: {source.status}",
                    f"Inclusion: {'included' if source.included else 'excluded'}",
                    f"Type: {source.source_type}",
                    f"Parsed/indexed chunks: {chunk_count}",
                    f"Locator: {source.locator or 'none'}",
                )
            )
        )

    def _selected_source(self) -> SourceRecord | None:
        project_id = self.context.project_id
        value = self.query_one("#guided-source-picker", Select).value
        if project_id is None or not isinstance(value, str):
            return None
        return self.context.composition.service.get_source(project_id, value)

    @staticmethod
    def _import_summary(kind: str, summary: SourceImportSummary) -> str:
        imported = len(summary.imported)
        skipped = len(summary.plan.candidates) - imported
        return f"Imported {imported} {kind} source(s); skipped {skipped}."

    def _toggle(self) -> None:
        step = self.context.state.current_step
        for suffix in ("name", "topic", "audience", "description", "create"):
            self.query_one(f"#guided-project-{suffix}").display = step == "project"
        for selector in (
            "#guided-source-title",
            "#guided-source-text",
            "#guided-source-add-paste",
            "#guided-source-paths",
            "#guided-source-add-files",
            "#guided-source-urls",
            "#guided-source-add-urls",
            "#guided-source-picker",
            "#guided-source-summary",
            "#guided-source-details",
            "#guided-source-toggle",
            "#guided-source-delete",
        ):
            self.query_one(selector).display = step == "sources"
        self.query_one("#guided-research-policy", Select).display = step == "research"
        self.query_one("#guided-research-save", Button).display = step == "research"
