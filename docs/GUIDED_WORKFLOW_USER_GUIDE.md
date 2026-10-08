# Guided Textual workflow user guide

> **Implementation status (2026-10-08):** The guided interface is under active
> remediation. Use the authoritative
> [guided-workflow TODO](DEEP_DIVE_TUI_GUIDED_WORKFLOW_TODO_2026-10-08.md)
> for the exact acceptance status. A visible action is not, by itself,
> evidence that the entire end-to-end workflow is qualified.

## Starting the application

Install with `uv sync --frozen`, then run `uv run deeper-dive-tui`
(or launch the installed `deeper-dive-tui` executable).
Use a terminal at least **80 columns by 24 rows**; **100×30** is recommended.
Below 80×24 the wizard displays a resize warning while retaining its state.
The normal CLI entry point is `deeper-dive`.

## First-run setup: Quick versus Advanced

An installation without sufficient durable provider/model-role/default readiness
opens the eight-step First-run Setup wizard. **Quick Setup** offers
recommended choices and role assignments for a compatible provider; it does not
silently override an explicit provider choice. **Advanced Setup** exposes more
specific provider and role settings. **Skip Setup** takes you to Home without
claiming setup has been completed.

The setup flow covers runtime/FFmpeg and optional KittenTTS checks, choosing and
configuring an LLM, connection testing, a synthetic minimal model inference
test, model-role assignments, speech choice, default voices, and default duration
and research policy. Its final Ready summary is **recomputed from current
configuration and runtime readiness**, not a one-time success flag.

Ollama and llama-server can provide local model inference. OpenAI and other
OpenAI-compatible services require an explicit network choice, and some require
credentials. Cloud use is optional. Secrets are represented by environment
variable references; do **not** paste API key values into a provider-name,
model, or other normal configuration field. "No speech yet" is valid for
finishing setup, but audio generation will still require an appropriate TTS
route and FFmpeg. A disconnected or invalidated provider can cause setup to
show **Needs attention** again. Review the provider's health and role
assignments instead of relying on a previously completed setup screen.

## Home, Projects, and advanced navigation

Home promotes **New Deep Dive**, **Projects**, and **Library**, and presents
production-derived setup status and recent project/episode summaries.
**Resume Deep Dive** appears when a saved guided draft can be recovered.
Advanced actions provide Sources, Research, Hosts, Providers, Settings, Help,
and the existing Episode/Generate tools.

For the seven-step **New Deep Dive** workflow:

1. **Project Setup** — enter a project name, main curiosity/question, and
   audience. Creating the project writes to the normal project service.
2. **Sources** — import pasted text, local files/folders, or explicitly selected
   URLs. Included, indexed sources are required to satisfy the source step.
3. **Research** — select *Use only my sources*, *Fill important gaps*, or
   *Research extensively*. The last two can involve external network access
   subject to configured policy.
4. **Hosts** — create/reuse host profiles, choose one or more, and save their
   ordering for the episode. Preview a voice only when speech is configured.
5. **Episode Settings** — title, focus, audience, and duration presets;
   advanced fields include technical depth and must-cover/avoid constraints.
6. **Review & Plan** — build a persisted plan with the normal planning
   service. Review segments before continuing; plan mutation is restricted once
   generation has started.
7. **Ready to Generate** — review shared source, plan, host, provider, speech,
   network, and FFmpeg preflight results. Correct blockers before Generate.

**Generate Deep Dive** creates/reuses a normal durable run and moves to the
production-backed guided monitor. The monitor reports persisted stages and
unit progress **only where measurable**, plus pause, resume, and confirm-cancel
actions. Use **Repair Configuration** from a failed run to revisit an applicable
configuration screen. A completed run can open Episode Ready with Review,
Play, Export, and Library actions. Export is an **explicit** action: completing
the pipeline's informational `export` stage does not itself guarantee that
downloadable output files were exported.

**Quick Deep Dive:** the production `QuickDeepDiveService` applies a user/project
default duration, research policy, and hosts to a **normal draft episode**.
The guided one-click Quick shortcut and complete Quick-versus-guided
qualification are still TODO work. Do not interpret the existence of this
service as a finished end-to-end shortcut or an alternative generation engine.

## Keyboard and terminal controls

Use **Tab** / **Shift+Tab** for focus, **Enter** on a focused action,
**Space** to activate supported buttons/toggles, arrow keys to navigate
select/radio choices, and **F1** or **?** for context help. **Escape** is
the wizard's Save and Exit action outside any cancellable modal. A visible
step/progress marker includes text and symbols rather than relying only on
color. **Ctrl+G** opens New Deep Dive in the guided app.

## Save and Exit, restart, and repair

**Save and Exit** writes a small versioned checkpoint with only the wizard
location, setup mode, and durable production IDs; it does not copy providers,
source text, host records, plans, credentials, or audio into a separate wizard
database. Project creation, source imports, host choices, and other operations
persist at their normal production save boundaries. **Unsaved text typed
into form controls is not part of a durable draft**: save the production
operation before exiting.

**Resume Deep Dive** uses the checkpoint's location as a *hint* and reloads
current production prerequisites. If a source/project/episode prerequisite has
disappeared or become invalid, the wizard returns to the earliest incomplete
step instead of blindly jumping past it. Invalid or obsolete checkpoints fail
safely. If a run is already in progress or paused, use the run/monitor and
Library controls appropriate to its durable state rather than creating a
duplicate run.

When generation/preflight fails, inspect the sanitized error/stable failure code,
verify inclusion/index readiness of sources, host selection, model-role/voice
routes, and FFmpeg. A pause or retry is allowed only where the durable run
state permits it; cancelled runs cannot simply be resumed.

## Shared services, provenance, and privacy

Guided TUI and CLI workflows use shared production project/source services,
`EpisodePlannerService`, preflight, run creation, `PipelineOrchestrator`,
and episode export. The wizard is a navigation layer, not another persistence
or generation engine. Sources retain their inclusion/provenance identity.
Remote provider/research choices can transmit source-derived material to a
network service. Check explicit routing and research settings before enabling
remote behavior. See [provider configuration](PROVIDERS.md),
[production generation](PRODUCTION_GENERATION.md), and
[privacy/security](PRIVACY_SECURITY.md).
