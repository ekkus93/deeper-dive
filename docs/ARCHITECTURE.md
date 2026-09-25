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
