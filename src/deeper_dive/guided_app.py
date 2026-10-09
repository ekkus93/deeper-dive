"""Production entry point for the guided Textual startup workflow."""

from __future__ import annotations

from textual.binding import Binding

from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.guided_async_readiness import FirstRunReadinessCoordinator
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_generation import GuidedGenerationMonitorScreen
from deeper_dive.guided_home import add_new_deep_dive_action, refresh_goal_home
from deeper_dive.guided_readiness import ProductionWizardCompletion
from deeper_dive.guided_ready import GuidedEpisodeReadyScreen
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.preflight_screen import PreflightScreen
from deeper_dive.tui import DeeperDiveApp


class GuidedDeeperDiveApp(DeeperDiveApp):
    """Route first-run and New Deep Dive through the shared production context."""

    BINDINGS = [
        *DeeperDiveApp.BINDINGS,
        Binding("ctrl+g", "navigate('new')", "New Deep Dive"),
    ]
    SCREENS = {
        **DeeperDiveApp.SCREENS,
        "monitor": GuidedGenerationMonitorScreen,
        "ready": GuidedEpisodeReadyScreen,
    }

    def on_ready(self) -> None:
        self._draft_store = GuidedDraftStore(self.service.workspaces.data_dir)
        setup_context = self._draft_store.load(
            self.composition,
            WizardKind.FIRST_RUN,
            recover=False,
        ) or WizardContext(
            self.composition,
            WizardState(WizardKind.FIRST_RUN, "welcome"),
        )
        self._first_run_readiness = FirstRunReadinessCoordinator(setup_context)
        add_new_deep_dive_action(self)
        self.install_screen(
            GuidedFirstRunWizard(
                setup_context,
                self._first_run_readiness.completion,
            ),
            name="setup",
        )

        new_context = WizardContext(
            self.composition,
            WizardState(WizardKind.NEW_DEEP_DIVE, "project"),
        )
        self._new_context = new_context
        self.install_screen(
            GuidedEpisodeWizard(
                new_context,
                ProductionWizardCompletion(new_context),
            ),
            name="new",
        )

        self.call_after_refresh(lambda: refresh_goal_home(self))

        # Only a genuinely fresh installation enters setup automatically.
        # Returning users with invalidated providers can still inspect projects
        # and the Library, then explicitly resume setup from Home.
        config = self.provider_controller.config()
        returning_user = bool(
            config.providers or config.defaults or self.service.list_project_summaries()
        )
        if not returning_user:
            self.push_screen("setup")

    def action_navigate(self, destination: str) -> None:
        if destination == "setup":
            self.push_screen("setup")
        elif destination in {"new", "resume"}:
            if destination == "resume":
                restored = self._draft_store.load(self.composition, WizardKind.NEW_DEEP_DIVE)
                if restored is not None:
                    self._new_context.state = restored.state
                    self._new_context.project_id = restored.project_id
                    self._new_context.episode_id = restored.episode_id
                    self._new_context.run_id = restored.run_id
                else:
                    destination = "new"
            if destination == "new":
                self._new_context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "project")
                self._new_context.project_id = None
                self._new_context.episode_id = None
                self._new_context.run_id = None
            self.push_screen("new")
        elif destination == "quick":
            # Reuse the normal QuickDeepDiveService -> planner -> shared
            # preflight route; do not introduce a guided-only generation engine.
            selected = getattr(self.get_screen("home"), "selected_project_id", None)
            project_id = selected or self.current_project_id
            project = self.service.open_project(project_id) if project_id else None
            if project is None:
                self.action_navigate("new")
                return
            self.current_project_id = project.id
            self.current_project_name = project.name
            if not any(
                source.included and self.service.list_source_chunks(project.id, source.id)
                for source in self.service.list_sources(project.id)
            ):
                self.action_navigate("sources")
                return
            self.action_navigate("episode")
            self.call_after_refresh(self._launch_quick_deep_dive)
        elif destination == "projects":
            self.push_screen("home")
            self.call_after_refresh(lambda: refresh_goal_home(self))
        elif destination == "home":
            super().action_navigate(destination)
            self.call_after_refresh(lambda: refresh_goal_home(self))
        else:
            super().action_navigate(destination)

    def _launch_quick_deep_dive(self) -> None:
        screen = self.screen
        if isinstance(screen, EpisodeSetupScreen):
            screen.action_quick_deep_dive()
            self.call_after_refresh(self._start_ready_quick_deep_dive)

    def _start_ready_quick_deep_dive(self) -> None:
        # The normal Generate action owns shared preflight, duplicate-safe run
        # creation, and the production monitor/pipeline handoff. A blocked
        # preflight stays visible for configuration repair.
        screen = self.screen
        if isinstance(screen, PreflightScreen):
            screen.action_generate()


def main() -> None:
    GuidedDeeperDiveApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
