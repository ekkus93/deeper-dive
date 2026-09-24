# Deeper Dive Production Generation Correctness Remediation Spec

**Created:** 2026-09-24  
**Status:** Draft remediation authority for follow-up implementation  
**Related completed TODO:** `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md`  
**Follow-up TODO:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_CORRECTNESS_TODO_2026-09-24.md`

## 1. Purpose

The V1 integration remediation established a strong production-composition shell, durable SQLite repositories, provider registries, CLI/TUI service sharing, preflight checks, export artifacts, run-state control, redaction, and deterministic CI acceptance workflows. A follow-up code review found that several paths now called "production" still rely on deterministic harness behavior at the most important generation boundary.

This remediation corrects that gap. The production episode generation path must use resolved configured providers for host turns, directing/verification work where claimed, and TTS/audio synthesis. Deterministic providers must remain available for CI, but only as explicit provider-boundary adapters selected through durable configuration, not as hidden shortcuts inside the production pipeline.

## 2. Problem statement

Current master at the time of this spec contains the following correctness risks:

1. `ProductionComposition.generation_pipeline()` installs deterministic stage handlers that generate canned host turns and fake audio bytes internally.
2. `ProductionComposition.run_generation()` calls `effective_model_role_assignments_for_run()` but discards assignment errors.
3. CLI `episode generate` can start generation without enforcing preflight readiness or equivalent blockers.
4. CLI generation always creates a new run, while the TUI path has duplicate-run prevention semantics.
5. Several pipeline stages can be marked complete even when they only crossed a durable no-op boundary.
6. The pipeline `export` stage name can imply export work that is actually performed later through `episode export` or Episode Library export.
7. TTS artifact status values are inconsistent across paths (`complete` versus `completed`).
8. Provider UI/configuration does not expose all fields needed by supported adapters, including TTS voice catalog data and adapter metadata.
9. Existing tests prove durable deterministic output, but do not fail if hidden deterministic generation replaces configured provider-backed production behavior.
10. User/developer docs and final evidence language need to distinguish deterministic CI provider adapters from production stage shortcuts.

## 3. Design principles

- Production generation must be provider-backed. If a user configures providers and passes preflight, the pipeline must call those configured adapters rather than hidden deterministic generators.
- Determinism belongs at provider boundaries. CI can use fake LLM/TTS providers, but those fakes must be selected by durable provider configuration and invoked through the same registry/factory contracts as real providers.
- Preflight and generation must share one readiness contract. Anything that blocks preflight must also block CLI/TUI generation start.
- CLI and TUI must share generation start semantics. They should create/select/reuse/reject runs through one service rather than diverging.
- Stage names must mean real work. A stage may be a boundary only if that is documented and tested; otherwise it must perform the promised operation or be renamed.
- Artifact status values must be canonical and migration-safe.
- Documentation must not overclaim. Docs should explicitly describe deterministic CI adapters separately from real production adapters.

## 4. Scope

### In scope

- Replace hidden deterministic production generation handlers with provider-backed stage implementations.
- Introduce a shared generation readiness/start service used by CLI and TUI.
- Enforce fail-fast behavior when effective assignments contain unresolved roles, provider construction failures, or missing TTS voice/provider assignments.
- Make CLI generation duplicate-safe and preflight-equivalent.
- Make TTS generation route through configured host TTS providers and shared artifact/cache contracts.
- Canonicalize TTS artifact statuses and preserve compatibility with existing databases.
- Clarify or implement pipeline stage semantics for no-op boundaries and export.
- Expand provider UI/configuration coverage for supported adapter fields.
- Strengthen acceptance tests so hidden deterministic production shortcuts fail.
- Update user and developer documentation.

### Out of scope

- Rewriting all provider adapters from scratch.
- Requiring paid credentials or live external services in ordinary CI.
- Removing deterministic CI providers. They remain required, but must be explicit provider-boundary adapters.
- Changing the completed V1 integration remediation TODO history. This is a new follow-up remediation.

## 5. Required architecture changes

### 5.1 Provider-backed conversation generation

Introduce or extend a production conversation-generation stage that:

- Resolves the active episode, plan, hosts, and source/evidence context.
- Resolves the effective model-role assignments for the run.
- Constructs providers through the existing provider factory/registry.
- Calls configured adapters for host turn generation instead of a hidden deterministic turn provider.
- Uses directing and verification roles where the pipeline claims to support director/verification behavior.
- Persists generated turns with host identity, chapter/segment context, claims/evidence metadata, and source provenance.
- Returns actionable sanitized failure state if a configured provider is missing, unhealthy, unsupported, or returns invalid structured output.

Acceptance must fail if production generation writes a canned internal string that did not come from the configured provider adapter.

### 5.2 Provider-backed TTS and audio artifacts

Replace hidden fake-audio generation inside production stage handlers with a configured TTS stage that:

- Resolves each host's configured TTS provider and voice.
- Constructs TTS providers through the production provider factory/registry.
- Calls the shared TTS generation/artifact service or equivalent production contract.
- Writes canonical TTS artifacts and audio timeline entries.
- Reuses cache entries according to the canonical status vocabulary.
- Emits sanitized actionable failures for unsupported or misconfigured providers.
- Produces episode-level audio through the existing composition/export contracts, not by writing arbitrary placeholder bytes.

CI must still be deterministic by configuring deterministic fake TTS providers through durable configuration.

### 5.3 Shared generation readiness and start service

Add a service, tentatively `GenerationStartService`, responsible for starting generation from both CLI and TUI. It should:

- Run preflight or equivalent readiness checks.
- Treat blockers identically for CLI and TUI.
- Resolve or create a run according to a shared duplicate-safety contract.
- Reject illegal generation start states with actionable messages.
- Preserve pause/resume/cancel semantics.
- Return a structured result suitable for CLI JSON/text and TUI status/monitor navigation.

The existing TUI `select_or_create_generation_run()` logic should be folded into this shared service or made a thin wrapper around it.

### 5.4 Fail-fast assignment errors

`run_generation()` must not discard assignment errors. If effective assignment resolution returns any error that would have blocked preflight, generation must fail before mutating run state beyond a clear failed/rejected state. Tests must cover missing model-role assignments, invalid provider identities, unsupported provider capabilities, and missing TTS assignments.

### 5.5 Run duplicate-safety

Define the run selection policy once:

- If an episode has an active pending/running/paused run, generation start must reuse it or reject the new start according to the policy.
- If the latest run is completed/failed/cancelled, a new run may be created only when the command/action explicitly starts a new attempt.
- CLI and TUI must expose consistent behavior and status messages.

### 5.6 Pipeline stage semantics

Audit all pipeline stages. For each stage:

- If the stage performs real work, implement and test that work.
- If the stage is intentionally a boundary marker, document that explicitly and ensure tests do not treat it as proof of work.
- If `export` is not part of generation, rename or document it so users and tests do not confuse stage completion with artifact export.
- Completion state must mean that required work for that stage has completed or that the documented boundary semantics have been satisfied.

### 5.7 TTS artifact status canonicalization

Choose one canonical terminal success value for TTS artifacts. Migrate or normalize legacy values so repositories, cache lookups, export, timeline rendering, and tests agree. The repository should never miss usable cached artifacts because one code path wrote `complete` and another wrote `completed`.

### 5.8 Provider UI/configuration completeness

Provider management must support fields required by supported adapters, including:

- Concrete adapter identity.
- Base URL where applicable.
- Credential environment variable name where applicable.
- Default model where applicable.
- Voice catalog and default voice where applicable.
- Audio response format where applicable.
- Timeout and network-scope metadata where applicable.
- Health/discovery capability status and actionable unsupported-capability messaging.

Secrets must never be persisted into diagnostics or emitted in CLI/TUI output.

## 6. Testing and qualification requirements

### 6.1 Unit and integration tests

Add tests that fail if hidden deterministic production shortcuts are used:

- A configured fake LLM provider should receive the prompt/context and return a unique marker; persisted turns must contain that marker.
- A configured fake TTS provider should receive configured voice/text and return bytes/metadata; artifacts must reflect provider identity and configured voice.
- Missing role assignment errors must fail generation before output is produced.
- CLI and TUI generation must reject the same blocker set.
- Duplicate-run behavior must match between CLI and TUI.
- TTS artifact cache lookups must work for migrated/canonical statuses.

### 6.2 Acceptance workflows

Update deterministic acceptance workflows so they prove provider-backed production behavior while remaining offline:

- CLI acceptance must configure deterministic providers through durable config, pass preflight, generate via CLI, and prove provider callbacks were used.
- TUI acceptance must configure/select deterministic providers, start generation through the shared service, and prove provider-backed turns/audio were produced.
- Fresh-machine installed-wheel workflow must use installed entry points and assert provider-backed generation/export semantics without source-tree imports.

### 6.3 CI policy

Normal CI must not require paid credentials or live external services. Deterministic fake providers are acceptable only when configured as explicit provider adapters and invoked through production provider factories/registries.

## 7. Documentation requirements

Update user and developer docs to explain:

- Real production provider-backed generation flow.
- Deterministic CI/development provider adapters and how they differ from hidden shortcuts.
- Preflight/generation parity for CLI and TUI.
- Duplicate-run behavior.
- TTS provider/voice configuration.
- Pipeline stage semantics and export semantics.
- Artifact status compatibility and migration notes.

## 8. Completion criteria

This remediation is complete only when:

- Hidden deterministic production generation shortcuts are removed or confined to explicit configured test/development providers.
- CLI and TUI generation share readiness/start semantics.
- Generation fails fast on unresolved provider/model/TTS assignments.
- Provider-backed LLM/TTS generation is proven by tests and installed-wheel CI.
- Artifact statuses are canonical and migration-safe.
- Provider UI supports required fields for all supported adapter classes.
- User/developer docs reflect the corrected behavior.
- Exact-head CI passes, the remediation PR merges to `master`, the TODO is reloaded from merged `master`, and merged-master CI passes.
