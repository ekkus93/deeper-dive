# Deeper Dive TUI Guided Workflow Spec

**Created:** 2026-10-08
**Status:** Ready for implementation
**Applies to:** current Textual TUI on master at 37f7cd453fc333974934703e4f1a3b8ae7d48006
**Companion checklist:** docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_TODO_2026-10-08.md
**Predecessor:** docs/DEEP_DIVE_PRODUCTION_GENERATION_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-02.md

This specification defines a guided, keyboard-first Textual user experience for configuring Deeper Dive and creating episodes. It is a UX and workflow layer over the existing production services. It must not create a second provider, planning, generation, repair, or export implementation.

The approved UX intent is the terminal mockup discussed on 2026-10-08: a first-run setup wizard, a New Deep Dive wizard, a simplified post-setup dashboard, a generation-progress screen, an episode-ready result, and a simplified episode library. The image is design inspiration; this document is the implementation contract.

## 1. Problem statement

The current TUI exposes Deeper Dive primarily as a set of subsystem screens. Global navigation includes Home, Providers, Settings, and Help, while project navigation exposes Sources, Research, Hosts, Episode, Generate, and Library. Individual screens expose implementation concepts such as provider adapters, model roles, host IDs, policy strings, citation behavior, and low-level episode fields.

Those controls are useful for expert operation, but they require a new user to understand Deeper Dive's architecture before the user can accomplish the basic goal: supply material, choose how much research to perform, choose hosts, define an episode, review a plan, and generate it.

The guided workflow must make the normal path obvious, sequential, recoverable, and safe while preserving the existing advanced interfaces.

## 2. Product goals

The implementation must:

1. Make first-run configuration understandable without prior knowledge of provider adapters or model roles.
2. Make "create a Deep Dive" a guided end-to-end task rather than a scavenger hunt across unrelated screens.
3. Keep the application keyboard-first and appropriate for a terminal.
4. Preserve mouse support where Textual already provides it, but never require a mouse.
5. Reuse existing production state and production services as the source of truth.
6. Allow save/exit and deterministic resume from partial setup or partial episode creation.
7. Translate technical validation failures into actionable user-facing blockers without hiding diagnostic detail from advanced users.
8. Keep Quick Deep Dive as a convenience path into the same durable production workflow.
9. Keep advanced Sources, Research, Hosts, Providers, Settings, planning, review, and library operations available.
10. Preserve CLI behavior and all existing project data.
11. Preserve production security/redaction guarantees on every new wizard surface.
12. Be testable with deterministic Textual pilot tests and production-service acceptance tests.

## 3. Non-goals

This work does not:

- replace Textual with a GUI or web application;
- create graphical, mouse-first widgets that depend on pixel positioning;
- redesign the provider runtime, planner, pipeline, export format, or storage model except where a small wizard-state record is demonstrably necessary;
- remove expert configuration capabilities;
- duplicate production state inside wizard-only objects;
- bypass preflight, planning, provider factories, GenerationStartService, PipelineOrchestrator, EpisodeExporter, or existing repositories;
- silently weaken local-only or network-scope policy;
- require cloud providers or paid credentials;
- make Quick Deep Dive a separate generation engine.

## 4. Current architecture to preserve

The guided workflow should compose the existing application rather than replace it. Important existing boundaries include:

- DeeperDiveApp and the Textual Screen navigation shell;
- DeeperDiveService for project and source workflows;
- ProductionComposition as the typed production application context;
- ProviderController and provider factory/runtime registries;
- the existing first-run readiness logic in first_run.py;
- source/corpus services and durable project workspaces;
- research policy, research controller, and research execution services;
- host services and host presets;
- EpisodeConfigurationService;
- EpisodePlannerService and the existing episode plan controller/screen;
- PreflightService and the shared preflight presentation boundary;
- GenerationStartService and PipelineOrchestrator;
- GenerationMonitorController and durable run state;
- Transcript Review and targeted repair services;
- Episode Library and EpisodeExporter;
- QuickDeepDiveService and its normal production path.

Where a current screen directly implements behavior that belongs in a service, the wizard should call the service rather than copy the screen implementation.

## 5. Information architecture

### 5.1 Primary navigation after setup

The default top-level navigation should emphasize user goals:

- Home
- New Deep Dive
- Projects
- Library

A visually separate Advanced section should expose:

- Sources
- Research
- Hosts
- Providers
- Settings
- Help

The exact arrangement may be a left rail, a compact horizontal navigation, or another Textual layout that satisfies the terminal-size requirements below. The normal workflow must not present all advanced project subsystems as equal first-class choices before a project is selected.

### 5.2 Home/dashboard

After setup, Home should provide:

- a dominant New Deep Dive action;
- setup/readiness status;
- recent projects;
- recent episodes;
- the currently open project when applicable;
- obvious entry points to resume an incomplete New Deep Dive wizard;
- access to Advanced configuration without making it the visual default.

The dashboard must derive counts and status from current durable project/run state.

### 5.3 Returning users

Returning users with a valid configuration should land on Home, not the setup wizard.

Returning users whose previously valid configuration is no longer ready should see a prominent Setup needs attention state and a Resume Setup action. They should not be trapped in setup if they only want to inspect projects/library, unless a specific operation requires the missing dependency.

## 6. Shared wizard shell

Both wizards must use one reusable shell rather than independent navigation implementations.

### 6.1 Layout

At recommended terminal sizes, the shell should contain:

- header: product name, wizard name, and Step N of M;
- progress rail or compact progress row with completed/current/upcoming steps;
- main content panel;
- inline status/blocker area;
- Back and Continue actions;
- Save and Exit when state can be durably resumed;
- footer with context-specific keyboard hints.

Completed steps use both a symbol and text state. Current focus and completion must never be conveyed by color alone.

### 6.2 Keyboard contract

Every wizard screen must support predictable navigation:

- Tab: next focusable control;
- Shift+Tab: previous focusable control;
- Up/Down or Left/Right: move within radio/select/list choices where appropriate;
- Space: toggle checkboxes or multi-select items where appropriate;
- Enter: activate the focused primary action or select the focused row;
- Escape: cancel an open modal; otherwise Save and Exit or return to the previous safe boundary after confirmation when needed;
- F1 or ?: context help;
- screen-specific shortcuts may be added only when shown in the footer.

A user must be able to complete both wizards without a mouse.

Focus order must follow the visual reading order and must be deterministic under tests.

### 6.3 Transition contract

Continue is enabled only when the current step is complete or intentionally skippable.

When Continue is blocked, the screen must show the first actionable reason and retain focus/state. It must not navigate forward and then fail on the next screen.

Back must never discard already persisted production state.

Save and Exit must leave the workflow resumable. Unsaved text edits that are not yet durable must either be persisted as wizard draft data or trigger a concise confirmation before loss.

### 6.4 Progress semantics

The progress indicator is navigation/status, not an independent completion database.

A step is complete when the production state required by that step is valid. Examples:

- provider step complete: selected provider config is durably valid and runtime can be built;
- sources step complete: project exists and at least one included source is ready for the chosen path;
- hosts step complete: selected episode host set is valid;
- review step complete: a valid plan exists for the selected episode;
- ready step complete: shared preflight is Ready.

UI-only choices not represented by production state may use a small explicit wizard draft record, but that record must not duplicate providers, sources, hosts, episode configuration, plans, runs, or exports.

## 7. First-run Setup Wizard

The first-run wizard has eight primary steps.

### 7.1 Step 1 — Welcome

Purpose: explain what setup will do and choose setup depth.

Controls:

- Quick Setup — recommended;
- Advanced Setup;
- Continue;
- Skip Setup, if the user wants to inspect the application without generating.

Quick Setup uses recommended defaults and minimizes questions. Advanced Setup may reveal role assignment and provider-specific optional fields, but it should remain inside the same shell.

The screen must clearly state that local providers are supported and cloud services are optional.

### 7.2 Step 2 — System Check

Show readiness for required and optional local dependencies. At minimum:

- Python/runtime sanity;
- FFmpeg;
- KittenTTS availability;
- detected Ollama endpoint when available;
- detected llama-server endpoint when available.

Each row shows one of Ready, Optional, Missing, or Needs attention plus a concise explanation.

Missing optional components must not block unrelated configurations. For example, missing KittenTTS does not block a cloud TTS choice or No speech yet.

Provide a details action for diagnostic information and remediation instructions. Do not dump stack traces by default.

### 7.3 Step 3 — Choose AI Provider

Present user-oriented choices rather than raw adapter names:

- Ollama on this machine;
- llama-server;
- OpenAI;
- another OpenAI-compatible service;
- Configure manually.

Detectable local providers should be labeled as detected. The wizard should prefer local options in Quick Setup when they are healthy and compatible, but must not silently override an explicit user choice.

### 7.4 Step 4 — Configure Provider

Show only fields relevant to the selected provider.

Examples:

Ollama:
- base URL, prefilled from detection/default;
- model picker populated from discovery;
- Test Connection.

OpenAI:
- credential environment-variable reference, never raw credential persistence;
- model picker or model input;
- optional base URL only where supported.

OpenAI-compatible:
- base URL;
- credential reference when required;
- model;
- network-scope information.

The wizard must use the same transactional provider save/build boundary as the Providers screen. A failed test or save must leave prior durable configuration and runtime unchanged.

Provider-originated text must use the canonical sanitizer before display.

### 7.5 Step 5 — Test the language model

Run a small deterministic-purpose health/inference check through the configured provider boundary.

The UI shows:

- test prompt summary;
- running state;
- elapsed time when available;
- success with a short sanitized response preview;
- failure with an actionable sanitized message.

Quick Setup should then propose recommended model-role assignments using the selected model for compatible roles, including episode planning, host generation/conversation, directing, and verification where the production role policy allows.

Advanced Setup may edit role assignments here or link to the advanced role editor.

The wizard must not fake success by checking only that a model name is present.

### 7.6 Step 6 — Choose speech

Choices:

- KittenTTS local;
- OpenAI TTS;
- ElevenLabs;
- No speech yet;
- Advanced/Custom.

Show locality/network implications and whether credentials are needed.

If No speech yet is selected, setup may complete, but episode generation requiring audio must later surface the normal preflight blocker. The wizard must not mark TTS as Ready when it is intentionally absent.

### 7.7 Step 7 — Voice and defaults

For configured speech:

- choose default Host 1 voice;
- choose default Host 2 voice;
- Preview focused voice;
- optional A/B preview when practical.

Also collect or confirm a compact set of user-facing defaults:

- default episode duration preset;
- default research level;
- preferred local-only/network behavior when applicable;
- recommended host preset behavior.

Do not expose raw voice IDs as the primary label. Show friendly names with technical IDs only in details.

### 7.8 Step 8 — Ready

Summarize:

- language model and selected model;
- speech provider and selected voices, or speech intentionally deferred;
- FFmpeg;
- model roles;
- default research/duration choices;
- any nonblocking optional gaps.

Primary action: Create My First Deep Dive.
Secondary action: Go to Dashboard.

The readiness summary must be recomputed from current state on mount; it must not trust stale wizard completion flags.

## 8. New Deep Dive Wizard

The New Deep Dive wizard has seven primary configuration steps followed by generation/result screens.

### 8.1 Step 1 — Project Setup

Controls:

- project name;
- central topic/question or curiosity prompt;
- audience preset, such as General, Technical, or Expert;
- optional description.

The wizard may create the project at Continue or earlier when required for durable source state. If a project is created before the screen completes, Save and Exit must make it discoverable and resumable.

Provide an optional Quick Deep Dive path. Quick mode still creates normal durable project/episode state and uses production planning/preflight/generation.

### 8.2 Step 2 — Add Sources

Present task-oriented source actions:

- Files;
- Paste Text;
- URL;
- Folder, where supported by current source import behavior.

Show each added source with:

- friendly title/path/URL;
- indexing/readiness state;
- inclusion state;
- concise error state;
- optional details/provenance.

Actions:

- add;
- remove/delete with confirmation;
- include/exclude;
- inspect details;
- retry failed import/index where supported.

Continue is allowed only when the selected workflow has sufficient source state. If a source is still indexing, the UI should explain whether the user can continue or must wait based on actual production requirements.

The wizard must use existing source/corpus services rather than seed repository rows.

### 8.3 Step 3 — Research Settings

Replace free-form policy strings with user choices:

- Use only my sources;
- Fill important gaps — recommended;
- Research extensively.

Advanced research options may expose the existing research policy fields.

The UI should explain network implications before a research mode that requires external access is selected.

Research settings must map to the existing research policy/controller boundaries.

### 8.4 Step 4 — Choose Hosts

Present hosts as selectable terminal rows/cards with:

- display name;
- short behavior/personality summary;
- voice name;
- selected state;
- Preview Voice action.

Support at least:

- selecting one or more hosts;
- deterministic ordering;
- creating/editing a custom host through the existing host service;
- recommended presets.

Do not require a user to type comma-separated host IDs.

The selected host order becomes the episode host order through EpisodeConfigurationService.

### 8.5 Step 5 — Episode Settings

Collect user-facing episode configuration:

- episode title;
- main question/focus;
- duration presets such as 10, 20, 30 minutes plus Custom;
- target audience;
- optional technical depth;
- optional must-cover topics;
- optional avoid topics.

Hide low-level policy strings behind Advanced options.

Validate before persistence and use EpisodeConfigurationService for durable state.

### 8.6 Step 6 — Review and Plan

Build or load the plan through EpisodePlannerService.

Show an ordered, readable plan:

- segment number;
- title;
- approximate duration;
- short purpose/focus;
- optional lead host/evidence summary in details.

Actions:

- Edit Plan;
- Regenerate;
- regenerate/edit supported segment operations where allowed by current plan mutability policy;
- Continue.

The UI must respect the production plan-revision rules. If generation has started and plan mutation is prohibited, explain that policy instead of presenting a control that will fail mysteriously.

Continue requires a valid usable plan according to the shared plan-validity policy.

### 8.7 Step 7 — Ready to Generate

Run the same shared preflight used by CLI/TUI production generation.

Show each readiness item with:

- Ready;
- Needs attention;
- Optional.

Examples:

- sources ready;
- research policy ready;
- hosts selected;
- valid episode plan;
- model roles ready;
- provider health;
- speech/voice ready;
- FFmpeg ready;
- network/local-only compatibility.

Every blocker should expose an action that takes the user to the relevant wizard step or advanced screen when practical.

Primary action: Generate Deep Dive.
Secondary action: Save and Exit.

Generation must be started through GenerationStartService/shared production composition. No wizard-specific run creation path is permitted.

## 9. Generation Progress

After generation starts, navigate to a guided progress screen using durable run state.

Display the actual production stages and their current semantics. Do not imply that informational boundaries generated artifacts when they did not.

At minimum show:

- current stage;
- completed stages;
- elapsed time;
- progress where production can compute it honestly;
- latest safe/sanitized status message;
- pause/resume/cancel actions according to current run state;
- safe navigation away with the run continuing only when the current application execution model supports it.

The progress screen must survive screen recreation/restart by reloading the durable run state. It must not rely only on an in-memory task object.

Failures should show:

- stable stage;
- stable failure code when available;
- sanitized message;
- Retry/Resume when supported by durable pipeline semantics;
- Back to configuration when the blocker requires changing setup.

## 10. Episode Ready

On successful generation show:

- episode title;
- duration if available;
- selected hosts;
- audio playback control through existing playback behavior;
- Open in Review;
- Export Episode;
- View in Library.

The result screen must resolve the selected episode/run explicitly and preserve multi-episode isolation.

## 11. Episode Library

The simplified library view should prioritize episodes rather than raw project internals.

At minimum provide:

- recent episodes;
- episode title;
- project;
- generated/modified time;
- readiness/export status;
- Play;
- Open;
- Export;
- search/filter/sort where current data supports it.

The existing Episode Library production service/export behavior remains authoritative.

## 12. Quick Deep Dive integration

Quick Deep Dive remains a recommended shortcut, not a separate engine.

It may be entered from Home or the New Deep Dive wizard. It should:

1. create/use a normal project;
2. require or collect source material;
3. apply documented recommended research/host/episode defaults;
4. use EpisodePlannerService;
5. present at least a concise review or allow direct generation depending on the chosen Quick mode UX;
6. run shared preflight;
7. use GenerationStartService and PipelineOrchestrator;
8. produce normal durable runs, turns, audio, timeline, review state, and exports.

All existing QuickDeepDiveService production-path guarantees remain required.

## 13. Advanced mode and backwards compatibility

The current detailed screens remain available as Advanced interfaces.

Existing advanced users must still be able to:

- manage providers;
- manage Sources directly;
- run Research directly;
- manage Hosts;
- edit Episode configuration;
- inspect/edit plans where allowed;
- use Generate/Preflight/Monitor;
- review transcripts;
- use Library/Export;
- access Settings and Help.

The guided workflow may reorganize navigation, but it must not remove capabilities merely because they are not shown in the normal wizard.

Existing projects created before this feature must open without migration unless a migration is explicitly justified and tested.

Existing CLI commands and output contracts are outside the visual redesign and must continue to work.

## 14. Wizard state and persistence

### 14.1 Source of truth

Production data remains authoritative:

- projects and sources from project storage;
- providers from durable provider config;
- hosts from host storage;
- episode configuration from EpisodeConfigurationService;
- plans from plan storage/service;
- runs/checkpoints from pipeline storage;
- exports from export/library storage.

### 14.2 Minimal draft state

If the wizard needs to preserve UI-only draft information, define a small typed record containing only information not already represented by production state, such as:

- last wizard kind;
- last visited step;
- unsaved free-form topic text before a project is created;
- Quick versus Advanced setup preference;
- collapsed/expanded advanced sections.

Do not copy provider credentials, source content, host definitions, episode config, plan content, or run state into this record.

Draft state must be versioned if persisted. Invalid/old draft data must fail safe by returning the user to the earliest derivable valid step.

### 14.3 Resume rules

On resume, determine the earliest incomplete required step from production state, but preserve the user's later location when all prerequisites remain valid.

If a previously completed prerequisite becomes invalid, mark that step Needs attention and route Continue/preflight back to it.

## 15. Validation, errors, and recovery

All new user-visible provider/runtime errors must use canonical sanitization.

Use three levels:

- inline field validation for local input problems;
- screen-level actionable blocker for workflow problems;
- expandable diagnostic details for technical context.

Do not expose raw tracebacks in the normal flow.

Examples of actionable messages:

- "No language model is selected. Choose a model to continue."
- "Ollama is configured but cannot be reached at http://localhost:11434. Check that Ollama is running or choose another provider."
- "This episode has no valid plan. Return to Review & Plan."
- "Speech is not configured. Choose a speech provider or generate after configuring one."
- "FFmpeg is required to compose episode audio. Install FFmpeg, then run System Check again."

Where an existing error already has a stable code/message, reuse it.

## 16. Terminal layout and responsive behavior

The design target is a conventional terminal, not a large desktop canvas.

Requirements:

- Recommended viewport: at least 100 columns by 30 rows.
- Supported compact viewport: 80 columns by 24 rows.
- At compact size, collapse the progress rail to a single-line progress summary or abbreviated step list.
- Long content must scroll inside the main content region without hiding Back/Continue/footer actions.
- Horizontal scrolling must not be required for the primary wizard controls at 80 columns.
- Do not encode essential information solely in Unicode glyphs that become ambiguous without color; include text labels.
- Below the supported minimum, show a clear "terminal too small" message with the required minimum while preserving state.
- Layout tests must cover both recommended and compact sizes.

## 17. Accessibility and usability

The TUI must:

- have visible focus;
- have deterministic focus order;
- use text plus symbols for state, not color alone;
- avoid dense paragraphs where a short label plus help/details works;
- use consistent verbs across screens;
- keep the primary action in a consistent location;
- keep Back semantics consistent;
- provide help for domain terms;
- avoid raw IDs as primary labels;
- use confirmation for destructive actions;
- preserve typed input when validation fails;
- make loading/busy states obvious and non-interactive where duplicate actions would be unsafe.

No screen should require memorizing an undocumented shortcut.

## 18. Security and privacy

The wizard must preserve all current security rules:

- credential values are not persisted where references are required;
- provider text is recursively sanitized;
- URLs containing credentials are sanitized before display;
- run failures/statuses remain sanitized;
- cloud/network implications are disclosed;
- explicit local-only/network-scope settings remain authoritative;
- test prompts must not automatically include user source content unless the user is explicitly testing with that content.

First-run connectivity tests should use minimal synthetic content.

## 19. Testing strategy

### 19.1 Textual component tests

Add deterministic pilot tests for each wizard screen covering:

- mount/render;
- focus order;
- keyboard-only completion;
- Back/Continue;
- validation blockers;
- loading/success/error states;
- compact terminal layout;
- resume/re-entry.

### 19.2 First-run acceptance

A deterministic first-run acceptance fixture should prove:

1. clean config opens setup;
2. local fake/deterministic provider is configured through normal provider boundaries;
3. provider test succeeds;
4. recommended role assignments persist;
5. deterministic fake TTS/voice config persists;
6. Ready recomputes true state;
7. restart skips setup and opens Home;
8. invalidating provider readiness surfaces Setup needs attention.

Real Kitten qualification remains in the existing fresh-machine gate; ordinary wizard tests should remain deterministic and not require external downloads.

### 19.3 New Deep Dive acceptance

Reuse or extend the shared production acceptance fixture to drive the wizard through:

1. create project;
2. add/index source;
3. choose research policy;
4. choose hosts;
5. configure episode;
6. build valid plan through EpisodePlannerService;
7. pass shared preflight;
8. start generation;
9. produce multiple turns;
10. synthesize timeline/audio through production services;
11. reach Episode Ready;
12. export;
13. reopen from Library.

The test must prove that the wizard did not seed plan, run, turn, TTS, or export repository rows directly.

### 19.4 Recovery acceptance

Cover:

- provider failure during setup;
- source import/index failure;
- model discovery failure;
- speech/voice discovery failure;
- invalid episode field;
- invalid/missing plan;
- preflight blocker and repair navigation;
- generation pause/resume/cancel;
- durable failed run and supported resume;
- restart in the middle of setup;
- restart in the middle of New Deep Dive;
- restart during/after generation.

### 19.5 Compatibility acceptance

Prove:

- existing persisted projects open;
- existing provider configuration loads;
- existing hosts/episodes/plans/runs/timelines/exports load;
- advanced screens still operate;
- CLI acceptance remains green;
- current production-generation remediation tests remain green.

## 20. Documentation

Update user/developer documentation to describe:

- first-run setup;
- Quick versus Advanced setup;
- local versus cloud provider choices;
- New Deep Dive guided workflow;
- Quick Deep Dive shortcut;
- advanced navigation;
- keyboard controls;
- terminal-size requirements;
- save/resume behavior;
- troubleshooting common setup blockers;
- the rule that wizard flows reuse the same production services as CLI/advanced TUI.

## 21. Implementation sequencing

Prefer coherent vertical slices:

1. shared wizard shell, state derivation, keyboard/focus contract;
2. first-run setup wizard;
3. simplified Home/navigation;
4. New Deep Dive project/sources/research/hosts steps;
5. episode/review/preflight steps;
6. generation progress/result/library handoff;
7. Quick Deep Dive integration;
8. recovery/resume/compact-layout/accessibility hardening;
9. compatibility and regression qualification;
10. documentation and final exact-head closeout.

Do not split each individual wizard page into an isolated PR or branch when direct-master Ralph policy permits coherent master work.

## 22. Completion criteria

This guided-workflow remediation is complete only when:

- all companion TODO items are checked;
- first-run setup is fully usable with keyboard only;
- New Deep Dive is fully usable with keyboard only;
- both workflows resume from durable state;
- normal users no longer need raw host IDs or model-role knowledge to generate an episode;
- the shared preflight/generation/export production paths are used;
- Quick Deep Dive remains a normal durable workflow;
- advanced screens and CLI remain compatible;
- compact terminal and accessibility tests pass;
- security/redaction tests pass;
- full quality gates pass;
- installed-wheel fresh-machine acceptance passes;
- selected mandatory Kitten qualification passes;
- the final TODO reconciliation commit itself has exact-head CI evidence on master.
