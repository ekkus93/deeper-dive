# Architecture and developer guide

This guide documents the implementation structure for developers extending Deeper Dive. The product/design contract remains `docs/DEEP_DIVE_TUI_SPEC.md`; this file focuses on the codebase conventions, layer boundaries, persistence model, provider contracts, checkpointing, and test strategy used by the current implementation. Provider-backed production generation has a dedicated architecture note in `docs/PRODUCTION_GENERATION_ARCHITECTURE.md`.

## Layering and dependency direction

Deeper Dive keeps UI, application orchestration, domain objects, provider adapters, and persistence separated so the same engine can be used from both the Textual TUI and the CLI.

The intended dependency direction is:

```text
Textual screens / CLI commands
        -> application services and controllers
        -> domain services / orchestration
        -> provider contracts and storage repositories
        -> SQLite / filesystem / external provider adapters
```

Important rules:

- Textual screens should not call live LLM, TTS, research, or audio providers directly.
- CLI commands should use the same application/service boundaries as the TUI where possible.
- Domain services should operate on explicit records, value objects, repositories, or provider protocols rather than UI widgets.
- Persistence code should not import Textual.
- Provider adapters should satisfy normalized provider protocols and should keep provider-specific details behind those protocols.
- Fake providers should remain first-class so CI can exercise workflows without network credentials or model downloads.

When adding a feature, prefer a small service/controller with deterministic unit tests first, then wire it into TUI and CLI surfaces.

## Production composition root

`ProductionComposition.build` is the production object graph entry point for product surfaces that need shared services. It initializes the workspace, loads persisted configuration, builds provider registries through `ProviderFactory`, and exposes the shared provider controller, research controller, preflight controller, generation monitor controller, benchmark service, playback controller, and application service.

The TUI consumes this composition through `DeeperDiveApp`: injected controllers remain available for tests, but normal app construction receives the provider, research, preflight, generation-monitor, benchmark, and playback boundaries from the production composition root. CLI construction now also builds production composition once in `deeper_dive.cli.main`; project/source/host/episode commands use the composed application service, and research commands use the composed `research_controller` instead of creating a second `PersistentResearchController` path.

DDR-091 is not complete yet. Provider inspection in `deeper_dive.command`, episode planning, generation/run control, and export still contain command-local construction or placeholder paths. Those paths must be migrated or deliberately retained with narrow documentation before the duplicate-construction checklist can be closed.

## Domain model

Core concepts are represented as durable records and service-layer value objects:

- **Project**: a workspace rooted under the application data directory. It owns a project database and subdirectories for sources, cache, runs, transcripts, and output.
- **Source**: a primary or supplemental item with origin, title, locator, parsed text, inclusion state, and chunked evidence.
- **Research gap**: a persisted question or weakness discovered in the current corpus. Gaps can be listed, ignored, researched, or revisited.
- **Supplemental candidate/outcome**: the result of researching a gap, including accepted/rejected status and rationale.
- **Host**: a profile with display name, role, expertise, instructions, relationship/personality fields, and optional TTS provider/voice assignment.
- **Episode**: a configured deep dive under a project. Episode configuration includes focus, audience, target duration, style, hosts, research policy, and provider/model overrides.
- **Plan**: a structured set of episode segments produced before dialogue/TTS generation.
- **Run**: a checkpointed generation execution with current stage, state, completed stage units, failure metadata, and pause/cancel flags.
- **Transcript/turn**: generated host-attributed dialogue with evidence IDs and later citation/claim inspection.
- **Claim**: a material generated statement with verification state and supporting/contradicting evidence links.
- **Export**: final or reviewable artifacts such as transcript, metadata, source manifest, audio, and diagnostics.

The implementation often stores records as dataclasses and passes richer behavior through services/controllers. Keep record shape stable and explicit; do not hide persistent schema changes inside UI code.

## Provider contracts

Provider-neutral contracts are the seam between orchestration and runtime-specific implementations.

### LLM providers

LLM providers expose:

- a stable provider ID;
- health checks;
- model discovery;
- non-streaming generation;
- optional streaming generation;
- model capabilities such as structured output, streaming, and context size.

Generation requests use normalized messages, optional model selection, token/temperature hints, and optional structured-output schema. Provider adapters should convert those requests into provider-specific API calls and return normalized responses.

### TTS providers

TTS providers expose:

- a stable provider ID;
- health checks;
- voice discovery;
- synthesis requests with text, voice, optional model, format, and sample-rate hints;
- normalized audio results with media type, format, provider, voice, model, sample rate, and duration metadata.

TTS adapters must validate provider/voice selection before synthesis. They should return actionable errors rather than raw provider tracebacks on user-facing paths.

### Research/fetch providers

Automated research must use the research-safe fetch boundary. It validates HTTP/HTTPS URLs, rejects non-public address answers, validates each redirect target, enforces finite timeouts and byte limits, and accepts only expected text content types. Explicit user URL imports are a separate user-supplied source path and must not be used to bypass automated-research SSRF controls.

### Audio/process providers

External audio operations must construct argv lists and call subprocesses with `shell=False`. Paths and user-derived names are passed as separate argv elements, not interpolated into shell strings. FFmpeg and local playback both follow this pattern.

## Persistence and migrations

Each project has an isolated SQLite database under its project workspace. The workspace manager validates project IDs and rejects absolute/traversal project-relative paths.

Persistence guidance:

- Use repositories for database access; do not issue ad hoc SQL from TUI screens.
- Keep schema initialization and migrations deterministic.
- Use generated IDs for durable objects and sanitized readable names only for artifact filenames.
- Keep user configuration separate from project databases.
- Do not store credentials in project databases, normal config records, exports, or diagnostic bundles.
- On POSIX platforms, user config writes should preserve owner-only permissions where supported.
- Existing concrete provider configuration records should load with defaults for newly added optional fields.
- Ambiguous generic legacy provider types such as `llm` or `tts` must fail with actionable guidance rather than guessing a runtime adapter.

When adding a schema change:

1. Add the migration or initialization change.
2. Add repository methods around it.
3. Add tests for both new persisted data and upgrade/compatibility behavior where applicable.
4. Ensure stale cache/generated artifacts are invalidated if the persisted semantics change.

## Guided workflow and configuration invariants

`WizardShell` owns the shared Save-and-Exit confirmation and computes dirty
state from the current editable step's controls. Screens dispatch Save changes
through existing production controllers, not a second wizard database.
`GuidedDraftStore` stores versioned navigation hints and stable durable
IDs only; credential values and pasted source bodies are excluded. Completed
first-run setup and completed generation runs must not leave stale Resume
actions. An unavailable/deleted project invalidates an unrecoverable draft;
active or paused work remains resumable.

`ProviderConfig` validates environment-variable credential references and
structurally rejects URLs with userinfo or sensitive query parameters.
`UserConfigStore.save()` revalidates the complete mutable model immediately
before serialization to prevent post-construction mutation from bypassing
those checks. Multi-default updates should use one validated
`SettingsController.set_defaults()` transaction and one durable write.
Composite provider-plus-default actions use the same candidate-config rule:
validate the complete `UserConfig` first, then call `UserConfigStore.save()`
once. Do not sequence multiple `set_default()`/save calls for one user action;
a validation or filesystem failure must leave the previous in-memory and
on-disk configuration intact.
`deeper_dive.diagnostics.redact` is the canonical sanitization boundary for
recursive diagnostics and displayed error text; exception chains are sanitized
one message at a time. Any new TUI/CLI error presentation path must use it.

Quick Deep Dive resolves research mode from a project Quick override, an
explicit user Quick override, the user's global `research_policy`, and
finally the built-in Useful default. The guided Research selector must load
the durable project policy on revisit and must not overwrite that policy
merely by navigating to the screen.

### Second post-review durability and concurrency contracts

Guided edit state is represented by `WizardDirtyFormSnapshot`: wizard kind and step,
project/episode/entity target identity, the identity and raw control values last
hydrated from durable storage or accepted by a successful production save, current raw
displayed values, a separate normalized semantic projection, and the pending original
destination. Dirty detection compares raw displayed values with that durable baseline
and also detects target-identity changes; semantic normalization never makes unsaved
input appear clean. `WizardShell` owns the destination-aware Save/Discard/Cancel
transition contract, while concrete wizards contribute target identity and non-widget
state such as ordered host IDs. A pending transition retains its requested destination;
the snapshot detects target drift from the durable baseline, and record-selection
handlers preserve the original selection while its save/discard confirmation is open.
Baseline bookkeeping follows five rules (FPR-19). (1) `_form_baselines[step]` holds the
raw widget values last hydrated from durable storage or accepted by a successful
production save, and `_form_baseline_targets[step]` the record identity they belong to.
(2) Only these writers may change a baseline: `_remember_current_form()` (synchronous,
after hydration, a successful save, or a Discard restore); `_schedule_form_baseline()`
(deferred to after the next refresh, used on step arrival and Back, and a no-op when the
user has edited the form or a different baseline already exists);
`_remember_host_profile_baseline()` / `_remember_host_order_baseline()` (scope-limited to
the profile or the membership/order, so a profile-scoped Save or Discard cannot adopt the
other scope's edits); `_capture_preset_baseline()` (records the durable provider values
before an AI preset overwrites the controls, and pins the step in
`_preset_baseline_steps` so arrival never re-baselines the preset); and
`_rebaseline_steps()` (after app-initiated re-hydration such as screen resume, only for
steps that were clean beforehand). (3) User-typed values never become a baseline, and
Discard with no baseline fails closed by clearing the step's fields. (4) Forward
navigation baselines synchronously except for pinned preset steps. Back baselines on the
deferred path in the first-run wizard and the shared shell; the episode wizard re-hydrates
and baselines synchronously after Back. (5) Mounting runs once per screen: `WizardShell.on_mount`
calls the `_before_mount()` and `_mounted()` hooks, which subclasses chain with `super()`;
subclasses must not define `on_mount`, because Textual dispatches that handler on every
class in the MRO.

Step-specific saves return a typed `WizardSaveResult` so partial success is explicit. A multi-operation save must
either be transactional or leave the unsaved remainder dirty and retryable; UI status
text is never parsed to infer success.

`UserConfigStore` publishes JSON with a securely-created unique same-directory
temporary file, owner-only mode on POSIX, flush + file `fsync`, atomic
`os.replace`, and parent-directory `fsync` where supported. A per-path advisory
lock serializes cooperating writers, and the loaded content hash is an optimistic
revision token: a stale writer fails with `UserConfigConflictError` rather than
silently losing another update. Pre-replace failures preserve prior bytes and clean up
only the temporary file owned by that save. A failure after `os.replace` is reported
as uncertain durability, not falsely described as rollback. The parent config
directory is a same-user trust boundary; this does not defend against a fully
compromised process running as the same account.

`FirstRunReadinessCoordinator` is intentionally bounded. Identical fingerprints
coalesce callbacks; different fingerprints may supersede the visible generation but
cannot exceed the configured worker budget. Timeout timers are owned and cancelled,
late results are generation/fingerprint checked, app shutdown closes the coordinator,
and provider adapters themselves receive finite transport timeouts. Python cannot
safely kill an arbitrary blocked third-party call, so the invariant is bounded
outstanding workers plus adapter deadlines, not forced thread termination.

Episode configuration and plan persistence use SQLite `BEGIN IMMEDIATE` transactions
and optimistic episode-config revisions. A no-op configuration save returns without
rewriting or deleting the current plan. Any semantic draft configuration change is
plan-relevant today because the planner consumes the full
`EpisodeConfiguration.snapshot()`; the change atomically updates the episode/host
order and invalidates its old plan. Once any generation/conversation work exists,
configuration is frozen. Planning records the episode config revision before provider
generation and checks it again when persisting, so a concurrent episode edit cannot
publish a plan for stale inputs. Existing historical run/plan/transcript/audio/export
identities are not rewritten by later configuration operations.

Plan approval is a metadata-only compare-and-swap (`EpisodePlanRepository.approve`): it
updates the plan's status in place only while the episode revision is unchanged, so a
concurrent edit can never be followed by an approval that re-publishes a stale plan.
Callers pass the plan they showed the user (`reviewed_plan_id`); if another surface
replaced it, approval raises `EpisodeConfigurationConflict` instead of approving a plan
nobody reviewed. Re-approving an already-approved plan is an idempotent success (the
update is keyed on plan id and episode id, not on `status='draft'`). Segment
regeneration and edits read the configuration snapshot first and fail with the same
typed conflict if the plan was replaced or removed meanwhile.
Each plan records a SHA-256 digest of the episode configuration it was built from
(`episode_config_sha256` in `plan_json`), and `plan_validity` rejects a plan whose digest
no longer matches (plans saved before the digest existed stay usable).
Run creation is one `BEGIN IMMEDIATE` selection that rechecks the episode revision seen
at preflight and inspects every run of the episode: it returns the active run, and it
refuses to create another while any pending or running run has a cancel request
outstanding (a paused run executes nothing, so its cancel request is exempt) (`GenerationRunStillStopping`), because cancellation only takes effect at a
stage boundary. See `docs/GENERATION_RUN_SELECTION_POLICY.md`. The readiness
fingerprint is read without the config lock (`UserConfigStore.load_published`), so the
fingerprint computation itself never waits on a writer; other UI-thread paths still read
the locked `config()`. The typed dirty-form snapshot (`WizardDirtyFormSnapshot`) is the
shared contract for Save/Discard/Cancel (TPR-17).

## Checkpointing and resume

Long-running generation uses durable run records and completed work-unit checkpoints. The pipeline has ordered stages such as sources, research, planning, conversation, verification, TTS, composition, and export.

Checkpointing rules:

- A stage should mark durable completion only after its output is committed.
- Resume should skip completed valid stages and continue from the first incomplete or invalidated stage.
- Pause and cancel are cooperative control flags checked at safe stage boundaries.
- Failures should record sanitized failure code/message and leave enough state for review/retry.
- Retrying should not regenerate already-completed artifacts unless requested or invalidated.

If a new stage is added, it should have an idempotent handler, durable outputs, progress events, and tests proving skip/resume behavior.

## Production generation architecture

Provider-backed production generation is documented in `docs/PRODUCTION_GENERATION_ARCHITECTURE.md`. That document covers the shared generation start service, provider-backed generation and TTS stage contracts, stage/export semantics, TTS artifact status compatibility, persisted-data compatibility policy, and deterministic provider-boundary testing strategy.

## Adding a new LLM provider

1. Implement the normalized LLM provider protocol.
2. Provide a stable provider ID and health check.
3. Implement model discovery or return a clear reduced-capability result if discovery is unavailable.
4. Map normalized requests into provider-specific requests.
5. Normalize response text, usage, model name, and structured-output metadata.
6. Keep credentials outside normal config/project databases.
7. Add fake or mocked tests that do not require network access.
8. Wire the provider into the provider controller/registry path and provider documentation.
9. Ensure preflight can disclose whether the provider route is local or remote.

## Adding a new TTS provider

1. Implement the normalized TTS provider protocol.
2. Provide a stable provider ID and health check.
3. Implement voice discovery.
4. Validate requested voice/model before synthesis.
5. Normalize audio bytes and metadata.
6. Return actionable user errors for common configuration, voice, runtime, and network failures.
7. Add deterministic tests with fake audio data.
8. Wire the provider into host voice assignment, preflight, and provider documentation.
9. Ensure generated audio artifacts include enough metadata for review/export.

## Adding a parser

1. Keep parser output bounded and project-scoped.
2. Preserve source origin, locator, title, and parse status.
3. Do not write temporary files outside controlled/project-owned locations unless cleanup and path-safety are explicitly reviewed.
4. Normalize parser failures into actionable user-facing errors while preserving sanitized diagnostics.
5. Add tests for successful parsing, unsupported/corrupt input, and path traversal/temporary-file safety where relevant.
6. Ensure parser output feeds chunking/indexing consistently.

## Testing with fake providers

Normal CI must not require network access, cloud credentials, GPUs, live LLM/TTS providers, or model downloads. Use fake providers and deterministic fixtures by default.

A good fake-provider test should:

- use deterministic source text and expected outputs;
- run inside a temporary data directory;
- avoid sleeping or timing assumptions;
- verify durable repository state as well as user-facing output;
- assert provenance/citation/diagnostic metadata when relevant;
- prove no credentials or source text leak into diagnostic bundles unless explicitly opted in.

Live-provider tests should be opt-in and separated from ordinary CI.

## Review checklist for new code

Before merging an architectural change, verify:

- the UI remains a client of application/domain services;
- CLI and TUI behavior share service logic where feasible;
- persistent data has repository coverage;
- provider credentials are not stored or exported by default;
- errors are actionable and diagnostics are sanitized;
- long-running work is checkpointed or explicitly bounded;
- fake-provider CI remains deterministic;
- documentation and provider/privacy guidance stay current.

## Readiness probe time bound

First-run readiness runs on worker threads and is shown through a UI deadline
(`FirstRunReadinessCoordinator.timeout_seconds`, default 8 s). Each real HTTP
request made by a probe uses a socket timeout of `min(timeout_seconds / 4, 1.0)`
seconds, and the calls inside one probe run sequentially. The worst-case probe
duration is therefore `(number of provider calls) x (per-request timeout)`, which
is also capped by an aggregate budget: the isolated probe controller carries a
monotonic deadline (`probe_deadline`, set to the UI timeout after the isolated adapters
have been built, so it ends slightly later than the UI deadline) and, once it has
passed, adapter lookups (`llm()`/`tts()`) raise `TimeoutError`, so providers not yet
probed are reported not ready instead of starting new requests. A single in-flight
request can still run for its own socket timeout past the deadline, and one provider
lookup can issue both `health()` and `models()`, so the overrun is at most two
request timeouts. Providers whose adapter cannot be built are listed with a sanitized
reason (`ProviderController.build_failures`) in the first-run system check. The UI never
waits past the deadline: it reports a timeout and the worker finishes in the
background, occupying one of the bounded worker slots (`max_workers`) until it
returns. An explicit Retry while all slots are busy shows a "workers are still
finishing" message rather than starting another probe.

Factories advertise bounded probes with `supports_probe_timeouts` (inherited by
`ProviderFactory` subclasses). A provider that cannot be built for a probe (for
example a missing credential variable) is recorded in
`ProviderBuildResult.build_failures` and reported as not ready; other providers
are still probed.
