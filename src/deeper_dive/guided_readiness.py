"""Production-derived completion probes for the guided Textual workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.first_run import FirstRunController
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.guided_workflow import WizardContext, WizardKind
from deeper_dive.model_roles import (
    ModelAssignment,
    ModelRole,
    effective_model_role_assignments,
)
from deeper_dive.plan_validity import evaluate_episode_plan
from deeper_dive.provider_tui import ProviderController
from deeper_dive.research_policy import ResearchMode, ResearchPolicyStore
from deeper_dive.source_readiness import source_index_ready
from deeper_dive.user_config import ProviderConfig

_FIRST_RUN_REQUIRED_ROLES = (
    ModelRole.EPISODE_PLANNING,
    ModelRole.HOST_GENERATION,
    ModelRole.DIRECTING,
    ModelRole.VERIFICATION,
)


@dataclass(frozen=True, slots=True)
class FirstRunDerivedReadiness:
    """Current setup readiness derived from durable config plus runtime probes."""

    llm_provider_ready: bool
    model_roles_ready: bool
    speech_choice_made: bool
    speech_deferred: bool
    audio_ready: bool
    ffmpeg_available: bool
    kitten_available: bool
    defaults_ready: bool

    @property
    def setup_ready(self) -> bool:
        """Whether first-run setup may be considered complete right now."""

        speech_runtime_ok = self.speech_deferred or self.audio_ready
        return (
            self.llm_provider_ready
            and self.model_roles_ready
            and self.speech_choice_made
            and self.defaults_ready
            and speech_runtime_ok
        )


def first_run_readiness(context: WizardContext) -> FirstRunDerivedReadiness:
    """Recompute first-run completion from production state; never trust a completion flag."""

    composition = context.composition
    controller = composition.provider_controller
    config = controller.config()
    status = FirstRunController(controller).status()

    llm_runtime: dict[str, frozenset[str]] = {}
    for name, provider in config.providers.items():
        if controller.capability(provider.provider_type) != "llm":
            continue
        llm_runtime[name] = _llm_runtime_ready(controller, name)

    llm_provider_ready = any(llm_runtime.values())

    assignments, assignment_errors = effective_model_role_assignments(user_defaults=config.defaults)
    model_roles_ready = not assignment_errors and all(
        _assignment_targets_ready_llm(
            controller,
            config.providers,
            llm_runtime,
            assignments.resolve(role),
        )
        for role in _FIRST_RUN_REQUIRED_ROLES
    )

    speech_deferred = config.defaults.get("speech_setup", "").strip().lower() == "deferred"
    tts_provider_id = config.defaults.get("tts_provider", "").strip()
    tts_voice = config.defaults.get("tts_voice", "").strip()
    tts_config = config.providers.get(tts_provider_id)
    tts_provider_configured = (
        tts_config is not None and controller.capability(tts_config.provider_type) == "tts"
    )
    speech_choice_made = speech_deferred or tts_provider_configured

    kitten_required = (
        tts_provider_configured
        and tts_config is not None
        and tts_config.provider_type.strip().lower().replace("_", "-") == "kitten"
    )
    tts_runtime_ready = (
        tts_provider_configured
        and bool(tts_voice)
        and _tts_runtime_ready(controller, tts_provider_id, tts_voice)
        and (not kitten_required or status.kitten_available)
    )
    audio_ready = tts_runtime_ready and status.ffmpeg_available

    defaults_ready = _defaults_are_valid(config.defaults)

    return FirstRunDerivedReadiness(
        llm_provider_ready=llm_provider_ready,
        model_roles_ready=model_roles_ready,
        speech_choice_made=speech_choice_made,
        speech_deferred=speech_deferred,
        audio_ready=audio_ready,
        ffmpeg_available=status.ffmpeg_available,
        kitten_available=status.kitten_available,
        defaults_ready=defaults_ready,
    )


def _llm_runtime_ready(
    controller: ProviderController,
    name: str,
) -> frozenset[str]:
    """Return healthy discovered models without requiring the default model.

    Explicit role assignments may target any discovered model, including when
    the provider's suggested default is unavailable or unset.
    """
    try:
        runtime = controller.llm(name)
        health = runtime.health()
        if not health.healthy:
            return frozenset()
        return frozenset(item.model for item in runtime.models())
    except (KeyError, OSError, RuntimeError, ValueError):
        return frozenset()


def _tts_runtime_ready(
    controller: ProviderController,
    provider_id: str,
    voice_id: str,
) -> bool:
    try:
        provider = controller.tts(provider_id)
        health = provider.health()
        if not health.healthy:
            return False
        return any(voice.id == voice_id for voice in provider.voices())
    except (KeyError, OSError, RuntimeError, ValueError):
        return False


def _assignment_targets_ready_llm(
    controller: ProviderController,
    providers: Mapping[str, ProviderConfig],
    runtime_ready: Mapping[str, frozenset[str]],
    assignment: ModelAssignment | None,
) -> bool:
    if assignment is None:
        return False
    provider = providers.get(assignment.provider)
    return (
        provider is not None
        and controller.capability(provider.provider_type) == "llm"
        and assignment.model in runtime_ready.get(assignment.provider, frozenset())
    )


def _defaults_are_valid(defaults: Mapping[str, str]) -> bool:
    duration = defaults.get("quick_deep_dive_duration_minutes", "").strip()
    if not duration:
        return False
    try:
        if int(duration) <= 0:
            return False
    except ValueError:
        return False
    research = defaults.get("research_policy", "").strip()
    if not research:
        return False
    try:
        ResearchMode(research)
    except ValueError:
        return False
    return True


@dataclass(slots=True)
class ProductionWizardCompletion:
    """Callable wizard completion probe backed only by current production state."""

    context: WizardContext

    def __call__(self, step_key: str) -> bool:
        if self.context.state.kind is WizardKind.FIRST_RUN:
            return self._first_run(step_key)
        return self._new_deep_dive(step_key)

    def _first_run(self, step_key: str) -> bool:
        readiness = first_run_readiness(self.context)
        if step_key == "welcome":
            return True
        if step_key == "system-check":
            return True
        if step_key == "ai-provider":
            return True
        if step_key == "provider-config":
            return readiness.llm_provider_ready
        if step_key == "model-test":
            return readiness.model_roles_ready
        if step_key == "speech":
            return readiness.speech_choice_made
        if step_key == "voice-defaults":
            return readiness.defaults_ready and (readiness.speech_deferred or readiness.audio_ready)
        if step_key == "ready":
            return readiness.setup_ready
        raise KeyError(step_key)

    def _new_deep_dive(self, step_key: str) -> bool:
        if step_key == "project":
            return self._project_ready()
        if step_key == "sources":
            return self._sources_ready()
        if step_key == "research":
            return self._research_ready()
        if step_key == "hosts":
            return self._hosts_ready()
        if step_key == "episode":
            return self._episode_ready()
        if step_key == "plan":
            return self._plan_ready()
        if step_key == "preflight":
            return self._preflight_ready()
        raise KeyError(step_key)

    def _project_ready(self) -> bool:
        project_id = self.context.project_id
        return (
            project_id is not None
            and self.context.composition.service.open_project(project_id) is not None
        )

    def _sources_ready(self) -> bool:
        project_id = self.context.project_id
        if project_id is None or not self._project_ready():
            return False
        sources = [
            source
            for source in self.context.composition.service.list_sources(project_id)
            if source.included
        ]
        return bool(sources) and all(
            source_index_ready(
                source,
                len(self.context.composition.service.list_source_chunks(project_id, source.id)),
            )
            for source in sources
        )

    def _research_ready(self) -> bool:
        project_id = self.context.project_id
        if project_id is None or not self._project_ready():
            return False
        return ResearchPolicyStore(
            self.context.composition.database_for_project(project_id)
        ).has_project_policy(project_id)

    def _hosts_ready(self) -> bool:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            return False
        repository = self.context.composition.service.hosts(project_id)
        episode = repository.get_episode(episode_id)
        if episode is None or episode.project_id != project_id:
            return False
        host_ids = repository.list_episode_host_ids(episode_id)
        return bool(host_ids) and all(
            (host := repository.get_host(host_id)) is not None and host.project_id == project_id
            for host_id in host_ids
        )

    def _episode_ready(self) -> bool:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            return False
        repository = self.context.composition.service.hosts(project_id)
        episode = repository.get_episode(episode_id)
        if episode is None or episode.project_id != project_id:
            return False
        try:
            config = EpisodeConfigurationService(
                self.context.composition.database_for_project(project_id)
            ).load_configuration(episode_id)
            config.validate()
        except (KeyError, ValueError):
            return False
        return True

    def _plan_ready(self) -> bool:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None or not self._episode_ready():
            return False
        return evaluate_episode_plan(
            self.context.composition.database_for_project(project_id),
            episode_id,
        ).usable

    def _preflight_ready(self) -> bool:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None or not self._plan_ready():
            return False
        try:
            return (
                GenerationStartService(self.context.composition)
                .preflight(
                    project_id,
                    episode_id,
                )
                .ready
            )
        except (KeyError, ValueError):
            return False
