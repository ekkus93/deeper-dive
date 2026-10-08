"""Production-backed first-run setup workflow."""

from __future__ import annotations

from time import monotonic
from typing import Protocol, cast

from textual.widget import Widget
from textual.widgets import Button, Input, Select

from deeper_dive.diagnostics import redact, sanitize_exception_message
from deeper_dive.first_run import FirstRunController
from deeper_dive.guided_workflow import CompletionProbe, WizardContext
from deeper_dive.llm import LLMMessage, LLMRequest
from deeper_dive.model_roles import ModelRole
from deeper_dive.settings_screen import SettingsController
from deeper_dive.wizard_shell import FirstRunWizardShell

_REQUIRED_SETUP_ROLES = (
    ModelRole.EPISODE_PLANNING,
    ModelRole.HOST_GENERATION,
    ModelRole.DIRECTING,
    ModelRole.VERIFICATION,
)


class _NavigationApp(Protocol):
    def action_navigate(self, destination: str) -> None: ...


class GuidedFirstRunWizard(FirstRunWizardShell):
    """Complete first-run flow routed through durable provider/settings boundaries."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe)
        self._llm_provider_name: str | None = None
        self._tts_provider_name: str | None = None
        self._model_test_identity: str | None = None
        self._model_test_summary = "Run a synthetic model test before continuing."
        self._model_options: tuple[tuple[str, str], ...] = ()
        self._voice_options: tuple[tuple[str, str], ...] = ()

    @property
    def settings(self) -> SettingsController:
        return SettingsController(self.context.composition.provider_controller)

    def step_controls(self) -> tuple[Widget, ...]:
        return (
            *super().step_controls(),
            Select(
                [
                    ("Ollama — local", "ollama"),
                    ("llama-server — local", "llama-server"),
                    ("OpenAI — cloud", "openai"),
                    ("OpenAI-compatible API", "openai-compatible"),
                    ("Manual / advanced", "manual"),
                ],
                value="ollama",
                allow_blank=False,
                id="setup-ai-choice",
