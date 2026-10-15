"""Production entry point for the guided Textual startup workflow."""

from __future__ import annotations

from textual.binding import Binding
from textual.css.query import NoMatches

from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.guided_async_readiness import (
    FirstRunReadinessCoordinator,
    FirstRunReadinessDispatch,
)
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_generation import GuidedGenerationMonitorScreen
from deeper_dive.guided_home import (
    GuidedHomeProjectsScreen,
    add_new_deep_dive_action,
    refresh_goal_home,
)
from deeper_dive.guided_readiness import ProductionWizardCompletion
from deeper_dive.guided_ready import GuidedEpisodeReadyScreen
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.preflight_screen import PreflightScreen
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.wizard_shell import WizardShell


class GuidedDeeperDiveApp(DeeperDiveApp):
    """Route first-run and New Deep Dive through the shared production context."""

    BINDINGS = [
        *DeeperDiveApp.BINDINGS,
        Binding("ctrl+g", "navigate('new')", "New Deep Dive"),
    ]
    HOME_SCREEN_CLASS = GuidedHomeProjectsScreen
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
        self._new_wizard_swap_pending = False
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

    async def _replace_new_wizard_then_push(self) -> None:
        """Replace the mounted New Deep Dive wizard with a freshly built one."""
        try:
            old = self.get_screen("new")
            pops = []
            # Save-and-Exit pushes Home over the wizard, so the old instance may
            # still be buried in the stack; Textual refuses to uninstall such screens.
            for _ in range(len(self.screen_stack)):
                if old not in self.screen_stack:
                    break
                pops.append(self.pop_screen())
            self.uninstall_screen("new")
            for pop in pops:
                await pop
            if old.is_attached:
                await old.remove()
            self.install_screen(
                GuidedEpisodeWizard(
                    self._new_context,
                    ProductionWizardCompletion(self._new_context),
                ),
                name="new",
            )
            self.push_screen("new")
        finally:
            self._new_wizard_swap_pending = False

    def on_first_run_readiness_dispatch(self, event: FirstRunReadinessDispatch) -> None:
        try:
            event.run()
        except NoMatches:
            # A fast background probe may complete before Textual composes the
            # installed setup screen. Ignore only that pre-composition race;
            # missing widgets on a composed screen remain actionable errors.
            setup = self.get_screen("setup")
            try:
                setup.query_one("#wizard-heading")
            except NoMatches:
                return
            raise

    def on_unmount(self) -> None:
        coordinator = getattr(self, "_first_run_readiness", None)
        if coordinator is not None:
            coordinator.close()

    def action_navigate(self, destination: str) -> None:
        screen = self.screen
        # Button events can be delivered around a synchronous screen push. Once
        # Resume has already installed the saved New Deep Dive wizard, treating a
        # duplicate resume as another external navigation would make the new
        # screen guard itself and can race its composition.
        if (
            destination == "resume"
            and screen is self.get_screen("new")
            and self._resume_is_current()
        ):
            return
        if isinstance(screen, WizardShell) and screen.request_external_navigation(destination):
            return
        if destination in {"new", "resume"} and self._surface_dirty_prior_wizard(destination):
            return
        # Guard the navigation boundary, not just one Home button: global nav,
        # shortcuts, and bubbled button events must not replace a saved flow.
        if destination == "new":
            home = self.get_screen("home")
            if (
                self.screen is home
                and isinstance(home, GuidedHomeProjectsScreen)
                and self._draft_store.has_resume(self.composition)
            ):
                home.action_request_abandon(start_new=True)
                return
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
            if (
                destination == "new"
                and screen is self.get_screen("new")
                and self._new_context.project_id is None
                and self._new_context.episode_id is None
                and self._new_context.state.current_step == "project"
            ):
                # Duplicate delivery of the same button press: the pristine new
                # wizard is already showing, so there is nothing to restart.
                return
            previous = self.get_screen("new")
            untouched = (
                self._new_context.project_id is None
                and self._new_context.episode_id is None
                and self._new_context.state.current_step == "project"
                and not (
                    isinstance(previous, WizardShell)
                    and previous.is_attached
                    and previous._current_form_dirty()
                )
            )
            if destination == "new":
                self._new_context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "project")
                self._new_context.project_id = None
                self._new_context.episode_id = None
                self._new_context.run_id = None
            # The context was just replaced by the app, not edited by the user.
            # A previously mounted wizard would carry the old project's widget
            # values, baselines, host order and confirmations, so it is replaced
            # by a freshly built instance once the old one has been removed.
            if previous.is_attached and not (destination == "new" and untouched):
                if not self._new_wizard_swap_pending:
                    self._new_wizard_swap_pending = True
                    self.call_later(self._replace_new_wizard_then_push)
            else:
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

    def _resume_is_current(self) -> bool:
        """True when the showing wizard already is the saved draft (a duplicate Resume).

        After a dirty wizard resolved its Save/Discard prompt for a Resume request,
        the wizard is still the current screen but may be at a different step than
        the draft; that Resume must run, not be swallowed as a duplicate.
        """

        restored = self._draft_store.load(self.composition, WizardKind.NEW_DEEP_DIVE)
        if restored is None:
            return True
        context = self._new_context
        return (
            restored.state == context.state
            and restored.project_id == context.project_id
            and restored.episode_id == context.episode_id
        )

    def _surface_dirty_prior_wizard(self, destination: str) -> bool:
        """Never silently reset a New Deep Dive wizard that holds unsaved edits.

        When the mounted wizard is buried under another screen and still dirty,
        bring it back and let its own Save / Discard / Cancel prompt (naming the
        project being edited) decide before the context is replaced.
        """

        candidate = self.get_screen("new")
        if not isinstance(candidate, WizardShell):
            return False
        wizard: WizardShell = candidate
        if (
            wizard is self.screen
            or not wizard.is_attached
            or wizard not in self.screen_stack
            or not wizard._current_form_dirty()
        ):
            return False
        while self.screen is not wizard and len(self.screen_stack) > 1:
            self.pop_screen()

        def prompt() -> None:
            if wizard.request_external_navigation(destination):
                project_id = self._new_context.project_id
                project = self.service.open_project(project_id) if project_id else None
                target = f"project '{project.name}'" if project else "a project not yet created"
                wizard.set_status(f"{wizard._last_form_status} Unsaved edits are for {target}.")

        self.call_after_refresh(prompt)
        return True

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
