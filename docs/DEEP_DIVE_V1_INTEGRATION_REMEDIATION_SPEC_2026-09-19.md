# Deeper Dive V1 Integration Remediation Specification

**Status:** Required remediation before V1 may again be declared complete  
**Date:** 2026-09-19  
**Applies to:** master beginning at commit `4370ac97f442db481efa221217d1da9b7a9fa2ab`  
**Companion plan:** `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md`  
**Original plan:** `docs/DEEP_DIVE_TUI_TODO.md`

## 1. Purpose

This specification defines the work required after the post-completion V1 code review.

The review found that many lower-level components are strong and reusable, but several production TUI and CLI paths stop at placeholder state changes, injected test doubles, or status messages instead of invoking the application services that already exist. The primary remediation theme is therefore **production composition and end-to-end integration**.

V1 is not considered remediated until the normal product paths can plan, generate, control, review, and export an episode using persisted configuration, and until CI proves those semantics on the exact commit being declared complete.

## 2. Preserve what already works

The remediation SHOULD preserve and reuse the existing:

- SQLite persistence and repository layer;
- provenance model;
- checkpoint and durable run-state model;
- pipeline orchestrator;
- exporter;
- provider abstractions and concrete adapters;
- KittenTTS benchmark service;
- audio playback abstraction;
- deterministic fake-provider testing strategy;
- credential-free normal CI.

A wholesale rewrite is not required.

## 3. Definition of done

A task may be marked complete only when all applicable conditions are true:

- production code uses the remediated path;
- unit/component tests cover local behavior;
- integration tests cover production wiring;
- negative paths are tested;
- user-visible behavior matches this specification;
- lint, formatting, type checking, tests, and build pass;
- exact-head CI passes;
- the change is merged to `master`;
- any TODO reconciliation commit itself receives exact-head CI.

A test that only asserts a label, status message, or newly-created pending record does not qualify an action whose contract is to perform work.

## 4. Production composition root

Introduce one explicit production composition path for both TUI and CLI.

It SHALL construct and connect:

- persisted application configuration;
- provider factory and registries;
- LLM providers;
- TTS providers;
- research/search/fetch providers;
- planning service;
- preflight service;
- pipeline orchestrator;
- episode exporter;
- transcript repair/regeneration service;
- TTS benchmark service;
- audio playback service;
- TUI controllers;
- CLI-facing service/controller objects.

The TUI and CLI MAY keep surface-specific controllers, but they SHALL share the same application services and provider construction. Deterministic fakes SHALL be explicit test/development substitutions at defined boundaries rather than silent production defaults.

## 5. Provider model and configuration

Persisted provider configuration SHALL carry a concrete adapter identity sufficient to instantiate the provider. Capability class and concrete adapter type SHALL not be conflated.

The provider factory SHALL:

- validate persisted configuration;
- instantiate the matching adapter;
- register it in the proper LLM/TTS/research registry;
- preserve local-versus-remote policy metadata;
- produce actionable sanitized errors;
- support deterministic fake adapters only when deliberately selected.

Where legacy records use ambiguous generic provider identities, the application SHALL migrate them safely or reject them with actionable conversion guidance.

## 6. Configuration precedence

Where provider/model/default overrides exist, effective precedence SHALL be:

1. episode override;
2. project override/default where supported;
3. user/application default;
4. documented built-in fallback only where explicitly intended.

Preflight, planning, and generation SHALL consume the same effective assignment resolution.

## 7. Settings TUI

Replace the placeholder Settings screen with a durable configuration interface covering settings already consumed by the product, including:

- provider setup and defaults;
- role/model assignments;
- host/TTS defaults where applicable;
- research/network policy defaults;
- Quick Deep Dive defaults;
- readiness/FFmpeg information;
- KittenTTS management/status entry points where appropriate;
- supported diagnostic/logging preferences.

Settings SHALL persist and SHALL be used by subsequent production composition.

## 8. Planning and preflight TUI

### 8.1 Episode planning

The Episode Setup "build plan" action SHALL:

1. persist episode configuration;
2. resolve effective hosts/providers/models;
3. invoke the shared production planning service;
4. persist the plan;
5. surface sanitized failures;
6. navigate to or refresh plan review.

A deterministic planner may remain as an injected test double but SHALL NOT be the unconditional production implementation.

### 8.2 Preflight

Preflight SHALL inspect the exact configuration that generation will use, including episode overrides.

On successful preflight, Generate SHALL start the normal generation workflow and navigate to/activate the generation monitor. It SHALL NOT stop after displaying a readiness message.

On blockers, generation SHALL remain blocked and the user SHALL receive actionable blocker text.

## 9. Generation monitor and run control

Production application construction SHALL supply Generation Monitor with a real runner backed by the pipeline orchestrator.

The monitor SHALL:

- launch generation asynchronously so the Textual UI stays responsive;
- display durable stage/run state;
- show recent turns and meaningful progress;
- request pause and cancel through real pipeline controls;
- resume paused/recoverable work by invoking orchestration from a durable checkpoint;
- open full transcript review;
- expose sanitized diagnostic/failure information.

Pause/resume/cancel state fields SHALL be consequences of orchestration, not substitutes for it.

## 10. Episode Library

Episode Library actions SHALL have real effects.

- Resume SHALL validate resumability and invoke the pipeline from checkpoint.
- Export SHALL invoke the shared exporter and create actual episode artifacts.
- Open/review SHALL bind review to the selected episode/run.
- Duplicate SHALL preserve intended configuration without copying run identity/artifacts.
- Delete SHALL retain confirmation behavior.

Tests SHALL assert durable state/artifacts rather than only status text.

## 11. Transcript Review and targeted regeneration

Transcript Review SHALL receive a production repair/regeneration service.

Turn/section regeneration SHALL:

- target the selected episode and exact scope;
- preserve unaffected content as required;
- update citations/provenance consistently;
- regenerate dependent audio when required;
- persist repaired state;
- surface sanitized failures.

The screen SHALL have direct component and integration tests.

## 12. Episode-specific audio selection

Playback/review SHALL resolve audio by durable artifact identity belonging to the selected episode/run.

The application SHALL NOT fall back to the first arbitrary audio file found in a shared project output directory. If the selected episode has no matching audio artifact, the UI SHALL report audio as unavailable.

Playback subprocesses SHALL also be cleaned up deterministically, with bounded terminate/wait/escalation behavior.

## 13. Quick Deep Dive

Quick Deep Dive SHALL use effective configured defaults. Built-in fallbacks remain:

- Curious Explainer + Skeptic;
- approximately 20 minutes;
- Useful research policy.

Configured overrides SHALL take precedence where supported.

Quick Deep Dive SHALL enter the same durable planning, preflight, generation, checkpoint, review, and export workflow as a manually configured episode. It is a convenience entry point, not a separate placeholder workflow.

## 14. Research CLI

The normal CLI SHALL construct the research controller/service with all required dependencies.

- `research analyze` SHALL invoke configured gap analysis and persist gaps.
- `research research` for selected/all gaps SHALL invoke configured research/search/fetch services and persist outcomes/supplemental sources.
- list/ignore/outcome operations SHALL continue to work on durable records.
- source origin/provenance SHALL be preserved.
- ordinary CI SHALL use deterministic fakes rather than live web APIs.

A controller with missing required callbacks SHALL not be considered a valid production implementation.

## 15. Episode CLI

### 15.1 Planning

`episode plan` SHALL invoke the same shared planning service as the TUI. The deterministic planner may remain only as an injected test double.

### 15.2 Generation

`episode generate` SHALL execute the shared pipeline. Merely creating a pending run record is not generation.

For the existing synchronous CLI contract, the command SHALL remain attached until a terminal or explicitly controlled state is reached unless a separately documented asynchronous job model is introduced.

Successful generation SHALL create durable generated episode state and appropriate transcript/audio artifacts.

### 15.3 Pause/cancel/resume

Control commands SHALL act on actual orchestration:

- pause requests a safe pause and reaches durable paused state;
- cancel requests cancellation and reaches the documented cancelled state;
- resume invokes the pipeline from a resumable checkpoint.

A command that only mutates a state field SHALL not qualify.

### 15.4 Export

`episode export` SHALL invoke the shared episode exporter and produce the same class of artifacts as TUI export, including applicable audio, transcript, provenance/source manifest, and metadata.

Metadata-only JSON does not satisfy episode export.

## 16. Provider CLI

Provider CLI operations SHALL resolve persisted provider configuration, instantiate the configured adapter through the shared provider factory, and invoke supported capabilities.

Required behavior includes:

- list durable configurations without exposing credentials;
- health/readiness testing;
- model discovery for supported LLM adapters;
- voice discovery for supported TTS adapters;
- explicit unsupported-capability errors;
- actionable sanitized configuration/connectivity/authentication errors.

Deterministic fake-provider paths may remain for CI but SHALL not be the only functioning paths.

## 17. KittenTTS benchmark

The benchmark command SHALL use the existing benchmark service or a shared equivalent.

It SHALL perform timed synthesis and report meaningful benchmark information, including:

- synthesis elapsed time;
- output audio duration;
- real-time factor or equivalent throughput;
- model/runtime/voice context;
- failure details.

Health/status output alone SHALL not be called a benchmark.

## 18. Shared export contract

TUI and CLI SHALL use one shared export implementation.

For a completed episode, export SHALL produce the artifacts already supported by the design, including applicable:

- final audio;
- transcript;
- source/provenance manifest;
- episode/run metadata;
- other existing deliverables.

Exports SHALL be episode-specific and use existing workspace/path rules.

## 19. Secret-safe failure handling

One canonical sanitization API SHALL be used before untrusted exception/provider text is:

- persisted;
- added to diagnostic bundles;
- logged;
- printed by CLI;
- rendered in TUI.

Regression tests SHALL cover representative credential-bearing authorization headers, API-key assignment forms, token assignment forms, environment-style secret assignments, credential-bearing URLs, and provider SDK exception text.

Pipeline failure persistence SHALL never store raw exception text without sanitization.

Sanitization SHALL preserve useful diagnostic context while removing secret material.

## 20. Static analysis

Review broad Ruff exclusions for core production modules.

For each excluded module:

- make it conform and remove the exclusion; or
- retain only a narrow documented exception with a bounded follow-up rationale.

Core CLI, preflight, diagnostics, audio playback, and transcript-review modules SHOULD not remain broadly excluded without justification.

## 21. Test strategy

### 21.1 Production-composition tests

Integration tests SHALL construct the application through the same composition path used in production, replacing external providers only at the provider boundary.

Tests SHALL not manually inject a runner/controller that production never constructs.

### 21.2 Semantic assertions

Tests SHALL assert promised outcomes.

Examples:

- Generate: pipeline executes and durable generated state/artifacts exist.
- Export: files exist and belong to the selected episode.
- Resume: orchestration resumes from checkpoint.
- Research: gaps/outcomes are actually produced.
- Provider CLI: configured adapters are instantiated and queried.
- Quick Deep Dive: configured overrides take effect and the normal durable workflow is used.

### 21.3 Multi-episode isolation

Create at least two episodes in one project and prove:

- independent run states;
- correct review binding;
- episode-specific playback;
- episode-specific export;
- no artifact cross-contamination.

### 21.4 Security regression

Inject representative credential-bearing failures and prove secret material does not appear in durable failures, diagnostics, captured logs, CLI output, or TUI-visible error state where practical.

## 22. Fresh-machine qualification

The final fresh-machine job SHALL install the built wheel into a clean Python 3.12 environment and use deterministic providers through the production composition path.

It SHALL:

1. create/configure a project;
2. import a local corpus;
3. configure providers;
4. configure hosts;
5. create an episode;
6. build/persist a plan;
7. run preflight;
8. execute generation to a real terminal state;
9. assert generated turns/transcript exist;
10. assert appropriate deterministic audio/artifact state exists;
11. export through the shared exporter;
12. assert expected export files/provenance exist;
13. assert the run is not merely left pending;
14. run at least one failure-sanitization probe.

The existing real KittenTTS CPU synthesis smoke may remain as a separate bounded provider/environment gate.

## 23. Documentation and compatibility

Update user and developer documentation for:

- provider types/setup;
- configuration precedence;
- research requirements;
- TUI generation flow;
- Quick Deep Dive overrides;
- CLI generation/control semantics;
- export contents;
- Kitten benchmark behavior;
- secret/error-redaction behavior;
- composition architecture and deterministic CI strategy.

Existing projects/episodes SHOULD remain readable. Any provider-identity schema/data change SHALL include migration or explicit compatibility handling and upgrade tests.

## 24. Final completion gate

Remediation is complete only when:

- every item in the companion TODO is checked and qualified;
- the affected DD-150, DD-151, DD-152, DD-153, DD-155, DD-161, DD-163, and DD-164 semantics are re-proven;
- DD-154, DD-160, and DD-162 regressions remain green;
- exact-head CI passes on the remediation branch;
- the remediation is merged to `master`;
- the TODO is reloaded from merged `master`;
- exact-head CI passes on merged `master`;
- fresh-machine qualification proves actual generation and export artifacts rather than placeholder records or messages.
