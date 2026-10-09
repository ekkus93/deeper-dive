# Guided Textual workflow user guide

> **Qualification status (2026-10-09):** The original guided workflow was
> implemented and qualified against its [2026-10-08 acceptance checklist](
> DEEP_DIVE_TUI_GUIDED_WORKFLOW_TODO_2026-10-08.md). An independent follow-up
> review found additional defects. The [post-review remediation checklist](
> DEEP_DIVE_TUI_GUIDED_WORKFLOW_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md)
> and its companion specification are now authoritative for remaining defects
> and final qualification. Prior acceptance does **not** imply remediation
> is complete.

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
   URLs. URL import contacts the external host; pasted text and local files
   do not require network access. Included, indexed sources are required.
3. **Research** — select *Use only my sources*, *Fill important gaps*, or
   *Research extensively*. The last two can involve external network access
   subject to configured policy.
4. **Hosts** — create/reuse host profiles, choose one or more, and save their
   ordering for the episode. Preview a voice only when speech is configured;
   cloud TTS previews can contact an external provider.
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

**Quick Deep Dive:** the Home shortcut requires an existing project with
indexed sources. It uses `QuickDeepDiveService` to apply the user/project
duration, research policy, and host defaults to a normal durable draft,
then builds the plan and runs **shared preflight**. When ready, Quick
automatically starts normal generation through `GenerationStartService`
and `PipelineOrchestrator`, with the same review, audio, and export behavior
as guided generation. If prerequisites are missing, the workflow shows
the normal source or preflight repair screen instead of starting a
placeholder run. Newly created recommended hosts inherit configured
first-run speech/voice defaults; existing host assignments are preserved.
The shortcut is not a separate generation engine.

For a new project's Research step, the selector uses its previously saved
project policy first, then the global user `research_policy`, then Useful.
For Quick Deep Dive, the precedence is **project Quick override > explicit
user Quick override > global user research policy > Useful**. An empty Quick
override counts as unset, not as a silent Useful override. Off disables
automatic supplemental research; Useful and Aggressive may contact configured
external services subject to network policy.

## Destructive actions

Advanced Providers, Hosts, and Sources require a separate, explicit
confirmation before removal. The first Remove/Delete action does not mutate
durable state; a subsequent Confirm applies only to the originally selected
target. Cancel is the default-safe action. Changing the target or repeating
confirmation after successful deletion does not delete another record.
Guided source deletion and project deletion likewise require confirmation.

## Keyboard and terminal controls

Use **Tab** / **Shift+Tab** for focus, **Enter** on a focused action,
**Space** to activate supported buttons/toggles, arrow keys to navigate
select/radio choices, and **F1** or **?** for context help. **Escape** is
the wizard's Save and Exit action outside any cancellable modal. A visible
step/progress marker includes text and symbols rather than relying only on
color. **Ctrl+G** opens New Deep Dive in the guided app.

## Terminal layout example

This is a **schematic ASCII example**, not a screenshot or a promise of
fixed widget widths. The same shared shell serves the eight-step First-run
wizard and the seven-step New Deep Dive wizard. Primary actions remain
outside the scrolling content region at 100×30 and 80×24.

```text
New Deep Dive — Step 6 of 7: Review & Plan
6/7 | ▶ Review & Plan (current) | ✓ 5 done

  Episode plan (scrollable)
  1. Opening — purpose and duration
  2. Evidence — purpose and duration
  [scrollable segment editor; inline validation appears by its field]

Status: Review the plan, then Continue.
[ Back ]  [ Continue ]  [ Save and Exit ]  [ Help ]
```

The real progress rail uses **text plus symbols** (complete, current,
upcoming, Needs attention); colors alone never convey prerequisite state.
At under 80×24, the wizard replaces the main content/actions with a
resize message without discarding its draft or durable production state.
Project and episode field validation appears beside the relevant form,
retains the user's typed values, and clears when the inputs are saved.

## Save and Exit, restart, and repair

**Save and Exit** writes a small versioned checkpoint with only the wizard
location, setup mode, and durable production IDs; it never copies provider
credentials, source text, host records, plans, or audio into a separate wizard
database. Project creation, source imports, host choices, and other operations
still use their normal production save boundaries.

When the current form has **unsaved edits**, Save and Exit (including Escape
outside a confirmation) presents **Save changes and exit**, **Exit without
changes**, and **Continue editing**. Continue editing is the non-destructive
default. Save changes validates and saves through the same production action as
the step's normal Save button. A validation or storage error keeps the entered
fields on the screen; no draft secretly captures credentials or pasted source
bodies. Explicit discard retains previously saved production data and only
loses the current unsaved input. When the current form is clean, Save and Exit
checkpoints and exits without extra confirmation.

**Resume Deep Dive** uses the checkpoint's location as a *hint* and reloads
current production prerequisites. If a recoverable source/episode prerequisite
becomes invalid, the wizard returns to the earliest incomplete step rather
than blindly jumping past it. A deleted project or a completed generation run
is not an incomplete workflow and does not remain resumable. Completing
first-run setup also clears its completed setup checkpoint. Invalid or
obsolete checkpoints fail safely. If a run is already in progress or paused, use the run/monitor and
Library controls appropriate to its durable state rather than creating a
duplicate run.

When generation/preflight fails, inspect the sanitized error/stable failure code,
verify inclusion/index readiness of sources, host selection, model-role/voice
routes, and FFmpeg. A pause or retry is allowed only where the durable run
state permits it; cancelled runs cannot simply be resumed.

## Shared services, provenance, and privacy

Guided TUI and CLI workflows use shared production project/source services,
