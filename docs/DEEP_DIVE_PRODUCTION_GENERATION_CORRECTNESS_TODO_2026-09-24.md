# Deeper Dive Production Generation Correctness TODO

**Spec authority:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_CORRECTNESS_SPEC_2026-09-24.md`  
**Created:** 2026-09-24  
**Purpose:** Fix follow-up code-review findings where production generation semantics are still satisfied by hidden deterministic shortcuts or incomplete readiness/configuration contracts.

## 0. Execution rules

- [ ] Treat this TODO as the authoritative remediation state for production-generation correctness.
- [ ] Do not modify or reopen the completed V1 integration remediation TODO except to reference this follow-up if needed.
- [ ] Use deterministic providers in CI only as explicit provider-boundary adapters configured through durable production paths.
- [ ] Do not mark an item complete because a deterministic hidden shortcut produces output.
- [ ] Require production wiring, tests, exact-head CI, merge to `master`, TODO reconciliation, reload from `master`, and merged-master CI before final completion.
- [ ] Keep CLI and TUI behavior aligned through shared services wherever practical.
- [ ] Preserve sanitizer, provenance, checkpoint, and artifact identity invariants.

---

# R1 — Provider-backed production conversation generation

## PCG-001 — Remove hidden deterministic host-turn generation from production stages

- [x] Identify every production generation path that instantiates or depends on hidden deterministic host-turn providers.
- [x] Replace hidden deterministic turn generation with configured provider-backed generation.
- [x] Keep deterministic behavior available only through explicit configured fake/development provider adapters.
- [x] Add a regression test that fails if production generation emits the old canned deterministic turn text without provider participation.

## PCG-002 — Resolve and use configured LLM role assignments during generation

- [x] Resolve effective model-role assignments for the run before conversation generation.
- [x] Construct provider adapters through the production provider factory/registry.
- [x] Use the configured host-generation role for host turns.
- [x] Use the configured directing role where director behavior is claimed.
- [x] Use the configured verification role where verification behavior is claimed.
- [x] Persist provider/model identity evidence with generated turns or run diagnostics where appropriate.
- [x] Add tests proving configured fake LLM providers are called and their unique output is persisted.

## PCG-003 — Preserve transcript provenance and structured output validation

- [ ] Preserve chapter, segment, host, claim, citation, and source-passage provenance in provider-backed generated turns.
- [x] Validate provider structured output before persistence.
- [x] Surface sanitized actionable failures for malformed provider output.
- [x] Ensure transcript review, repair, export, and multi-episode isolation still pass with provider-backed generation.

**Evidence:** PR #397 added `LLMHostTurnProvider` with model-bound structured-output validation and malformed-response rejection, passed exact-head CI run `36008687820`, merged as `a639d3a4622718160342cc3ffeb995f9d411b3b6`, and passed merged-master CI run `36008889541`. PR #398 removed the hidden production `_DeterministicHostTurnProvider` path, routes `_conversation_stage` through effective `HOST_GENERATION` assignments and the production LLM registry, keeps deterministic CI behavior only through configured fake providers, updated CLI/TUI/library/export/multi-episode/fresh-machine fixtures to configure `host_generation`, passed exact-head CI run `36049281542`, merged as `1ba83280f4ae5b8106cc25f14db613bf950d4825`, and passed merged-master CI run `36049471554`. PR #401 added durable turn-level provider/model identity evidence in `conversation_turn_provider_identity`, preserved existing `conversation_turns` schema shape, passed exact-head CI run `36052199820`, merged as `650e6c489862b39e7862cf7fce05d546ad158466`, and passed merged-master CI run `36052391424`. PR #403 added a production-composition regression proving malformed host-generation provider output fails the durable run at the `conversation` stage, persists sanitized actionable failure text, and does not leak the sentinel value, passed exact-head CI run `36057669855`, merged as `cee08359c75da396bd3576129f2f84cf0d1628f6`, and passed merged-master CI run `36066382235`. PR #422 added configured LLM adapters for directing decisions and transcript verification, routes production conversation generation through the configured `directing` role when present, routes the `verification` stage through the configured `verification` role when present, extends deterministic fake LLM providers only at explicit provider boundaries, and adds production tests proving configured director, host-generation, and verifier providers are called and that verification rejection fails before audio composition output is produced. Exact-head CI passed in run `36145962988`, PR #422 merged as `bf33737e22f26182c88214985a92cda048f74054`, and merged-master CI passed in run `36146139921`. Full source-passage provenance remains open.

---

# R2 — Provider-backed TTS and audio generation

## PCG-010 — Replace fake production audio byte generation

- [x] Identify production paths that write fake WAV or placeholder bytes directly.
- [x] Replace direct placeholder audio writes with configured TTS provider calls.
- [x] Preserve deterministic CI by configuring fake TTS providers through durable provider configuration.
- [x] Add tests that fail if production TTS bypasses the provider registry/factory.

## PCG-011 — Route host voices through configured TTS assignments

- [x] Resolve each host's TTS provider assignment and voice before synthesis.
- [x] Reject generation when a host has no usable TTS assignment and audio is required.
- [x] Support configured voice catalogs for local and remote TTS providers.
- [x] Persist provider, voice, cache key, and artifact identity consistently.
- [x] Add tests covering two hosts with distinct configured voices and providers.

## PCG-012 — Reuse shared TTS artifact/cache contracts

- [x] Route production synthesis through the shared TTS generation/artifact contract or equivalent service.
- [x] Reuse valid cached artifacts when appropriate.
- [x] Regenerate artifacts when transcript repair invalidates audio.
- [x] Preserve episode-specific audio identity and export behavior.
- [x] Add regression tests for cache reuse, repair invalidation, and export.

**Evidence:** PR #406 replaced `_tts_stage` direct deterministic WAV writes with `TTSGenerationStage`, routes production synthesis through configured `TTSProviderRegistry` providers, composes episode audio from persisted provider artifacts, keeps deterministic CI behavior through durable fake TTS provider configuration, and adds a regression asserting production TTS uses the provider generation contract rather than `_deterministic_audio_bytes` or `deterministic-tts`. It also fixed TTS cache reuse so valid cached provider audio can be reused without duplicate cache-key persistence, preserved multi-episode export/audio identity, aligned CLI/TUI/library/export fixtures with durable fake TTS configuration, passed exact-head CI run `36078189348`, merged as `ff0a4efb6998bbe537cb8f6fa4af8d5ec5277a53`, and passed merged-master CI run `36101809170`. PR #408 made fake TTS honor configured voice catalogs, preserved OpenAI-compatible remote voice-catalog validation, added a production-stage regression proving two hosts route through distinct configured TTS providers and voices, passed exact-head CI run `36102697707`, merged as `aa73adc0f1d4adea733ce1f9b2f056b18840b0a9`, and passed merged-master CI run `36102817118`. PR #410 removed the implicit first-provider/first-voice fallback by rejecting missing host TTS assignments when audio is required, added a missing-assignment regression, migrated CLI, export, production-composition, multi-episode, transcript-review, and DDR acceptance fixtures to explicit configured fake TTS assignments, and preserved transcript-repair audio invalidation/regeneration evidence through the production repair path. It passed exact-head CI run `36107870929`, merged as `8c41cc045bc2c4a5e681ab32a2a41e54e976b4c2`, and passed merged-master CI run `36108031085`.

---

# R3 — Shared readiness and generation-start semantics

## PCG-020 — Introduce shared generation start service

- [x] Create a shared generation readiness/start service used by both CLI and TUI.
- [x] Fold existing TUI generation-start selection logic into this service or wrap it thinly.
- [x] Make CLI `episode generate` call the shared service instead of directly creating a run.
- [x] Return structured results suitable for CLI JSON/text and TUI status/monitor navigation.

## PCG-021 — Enforce preflight-equivalent blockers in CLI generation

- [x] Run preflight or equivalent readiness checks before CLI generation starts.
- [x] Reject missing source, missing indexed corpus, missing hosts, missing provider/model assignments, missing TTS assignments, and FFmpeg blockers consistently with TUI.
- [x] Ensure CLI text and JSON errors are sanitized and actionable.
- [x] Add tests proving CLI and TUI reject the same blocker matrix.

## PCG-022 — Fail fast on assignment-resolution errors

- [x] Stop discarding errors returned by effective model-role assignment resolution.
- [x] Prevent generation from producing output when required roles are unresolved.
- [x] Persist or return a clear failed/rejected state without leaking secrets.
- [x] Add tests for missing role, invalid provider identity, unsupported capability, and missing TTS assignment.

**Evidence:** PR #412 introduced `GenerationStartService` as a shared CLI/TUI readiness and duplicate-safe start boundary, made CLI `episode generate` call it before running generation, routed TUI Generate through it when production composition is available, made `PreflightService` accept path-specific required model roles, preserved sanitized CLI failure behavior through `PreflightBlockedError`, and made `run_generation` fail fast on model-role assignment parsing errors. It also qualified CLI generation, CLI control, DDR-111 acceptance, and episode CLI fixtures against source/indexing, host/TTS, and FFmpeg readiness expectations. Exact-head CI passed in run `36120277010`, PR #412 merged as `b9bfd6f0e6632dbb51ff6452984c3a2b5eb26e4a`, and merged-master CI passed in run `36134160719`. PR #414 routed TUI preflight presentation through the same shared start service used by CLI generation and added `tests/test_generation_start_preflight.py`, a paired CLI/TUI blocker matrix covering missing sources, unindexed sources, missing hosts, missing TTS assignment, missing host-generation role assignment, invalid provider identity, unavailable model/capability, and missing FFmpeg. It also asserts shared start blocks before creating a run and keeps installed-wheel fresh-machine preflight aligned with generation-time `host_generation`/`tts` routes. Exact-head CI passed in run `36135204965`, PR #414 merged as `54e79005991b50b03c67eaf2d48efa30882aaa43`, and merged-master CI passed in run `36135379198`.

---

# R4 — Run lifecycle and duplicate-safety

## PCG-030 — Define one generation run selection policy

- [x] Document the run selection policy for pending, running, paused, failed, cancelled, and completed runs.
- [x] Reuse or reject active pending/running/paused runs consistently across CLI and TUI.
- [x] Allow new attempts after terminal states only through documented behavior.
- [x] Add tests for repeated CLI generate, repeated TUI Generate click, and mixed CLI/TUI starts.

## PCG-031 — Align status/control with duplicate-safe runs

- [x] Ensure `episode status` reports the correct active/latest run after duplicate-safe start logic.
- [x] Ensure pause/cancel/resume target the intended run.
- [x] Ensure Episode Library resume/export target the intended run and episode identity.
- [x] Add state-transition tests that include duplicate-start attempts.

**Evidence:** PR #412 extended `tests/test_generation_start.py` to cover the shared run-selection state matrix: pending/running/paused active runs are reused, completed/failed/cancelled terminal runs allow new pending attempts, cancellation-requested active runs are replaced by new attempts, and unknown persisted states fail closed. Exact-head CI passed in run `36120277010`, PR #412 merged as `b9bfd6f0e6632dbb51ff6452984c3a2b5eb26e4a`, and merged-master CI passed in run `36134160719`. PR #416 added `docs/GENERATION_RUN_SELECTION_POLICY.md` and `tests/test_generation_start_surfaces.py`, covering repeated CLI `episode generate`, repeated TUI Generate, mixed CLI→TUI duplicate starts, and CLI `episode status` reporting the reused active run identity. Exact-head CI passed in run `36136341618`, PR #416 merged as `fc07530bf7cc4581120b16a3d869c0552110bd3c`, and merged-master CI passed in run `36136474636`. PR #418 added state-transition targeting coverage for duplicate-start CLI pause/resume/cancel flows and Episode Library resume/export identity coverage, proving selected episode/run identity is preserved even when another episode is current. Exact-head CI passed in run `36137848055`, PR #418 merged as `9c809961baf780b5e6df666769d4b118f7c5fb29`, and merged-master CI passed in run `36138001916`.

---

# R5 — Pipeline stage semantics and export correctness

## PCG-040 — Audit pipeline stages for no-op completion claims

- [x] Enumerate every default pipeline stage and its handler.
- [x] For each no-op boundary, decide whether to implement real work, rename it, or document it as an intentional checkpoint boundary.
- [x] Update tests so boundary completion is not treated as proof of work.
- [x] Add a developer architecture note for stage semantics.

## PCG-041 — Clarify or implement generation pipeline export stage

- [x] Decide whether pipeline `export` performs artifact export or only marks generation completion readiness.
- [x] If export remains separate, rename or document the stage so users/tests do not confuse stage completion with exported artifacts.
- [x] If export is implemented in-pipeline, route it through `EpisodeExporter` and assert concrete artifacts.
- [x] Update CLI/TUI/fresh-machine tests to match the chosen semantics.

**Evidence:** PR #420 added `docs/GENERATION_PIPELINE_STAGE_SEMANTICS.md`, enumerating every default stage and handler, classifying `sources`, `research`, `verification`, and `export` as intentional durable readiness/checkpoint boundaries, and documenting that transcript/metadata/manifest/audio artifacts are produced by explicit CLI and Episode Library export services rather than by the generation pipeline `export` checkpoint. It also added `tests/test_generation_pipeline_stage_semantics.py`, which proves pipeline `export` completion alone does not create exported artifact files and that explicit export through `EpisodeLibraryExportService` produces the concrete transcript, manifest, metadata, and audio artifacts. Existing CLI, TUI, and fresh-machine workflows already perform explicit export after generation, matching the documented semantics. Exact-head CI passed in run `36138749603`, PR #420 merged as `a21c139b9041131d191d02c61261a358758d537b`, and merged-master CI passed in run `36138958158`.

---

# R6 — TTS artifact status canonicalization

## PCG-050 — Choose canonical TTS artifact success status

- [x] Choose one canonical terminal success value for TTS artifacts.
- [x] Update repositories, cache lookups, tests, export, timeline rendering, and docs to use it.
- [x] Add compatibility reads for legacy success values.
- [x] Add a migration/normalization path if persisted data requires it.

## PCG-051 — Add artifact-status compatibility tests

- [x] Test cache lookup for canonical success status.
- [x] Test lookup/normalization for legacy success status values.
- [x] Test export and timeline behavior with migrated/legacy artifacts.
- [x] Ensure no code path writes a noncanonical success status after remediation.

**Evidence:** PR #383 added canonical `TTS_ARTIFACT_STATUS_COMPLETE` handling, repository read compatibility for legacy `completed` rows, and write-time normalization, then merged as `4fd33e7c83e12587491bd9c637d594b4a83d8304` with merged-master CI run `35983971158`. PR #384 updated the remaining known production writer, CLI/pipeline assertions, and installed-wheel smoke to use the canonical success status, then merged as `629db8dfc2ada3150089dedd26e5dba1bc433702` with merged-master CI run `35987826239`. PR #388 added workspace-level legacy artifact cache/timeline/export compatibility coverage, then merged as `f3dafdc0096d25a662fb8fc7e589ed58e1adcf85` with merged-master CI run `35992678750`. This reconciliation adds the architecture documentation status contract and requires exact-head and merged-master CI before R6 remains closed.

---

# R7 — Provider UI and configuration completeness

## PCG-060 — Expand provider configuration model coverage in UI

- [x] Add UI/controller support for credential environment variable names where applicable.
- [x] Add UI/controller support for provider timeout and network-scope metadata where applicable.
- [x] Add UI/controller support for TTS response format where applicable.
- [x] Add UI/controller support for voice catalogs and default voices where applicable.
- [x] Ensure unsupported fields are hidden or explained per adapter type.

## PCG-061 — Validate provider UI save/reload/health for supported adapter classes

- [x] Test OpenAI-style LLM configuration through UI/controller.
- [x] Test Ollama configuration through UI/controller.
- [x] Test OpenAI-compatible local LLM configuration through UI/controller.
- [x] Test KittenTTS configuration through UI/controller.
- [x] Test OpenAI/OpenAI-compatible TTS configuration through UI/controller.
- [x] Test ElevenLabs-style TTS configuration through UI/controller.
- [x] Assert no credential value is emitted in diagnostics, logs, CLI, or TUI messages.

**Evidence:** PR #424 exposed the existing extended `ProviderController` configuration surface in the Providers TUI: credential environment variable names, timeout seconds, network scope, TTS response format, comma-separated voice catalogs, default models, and adapter-specific supported/ignored-field presentation. It added TUI regressions proving supported fields are persisted/reloaded through production provider factories and unsupported KittenTTS fields are ignored or explained instead of persisted. Exact-head CI passed in run `36176197791`, PR #424 merged as `62c11af77b293395e625f16de2c0dd927281f018`, and merged-master CI passed in run `36176383008`. PR #425 added a Providers TUI save/reload/health matrix covering OpenAI-style LLM, Ollama, OpenAI-compatible local LLM, KittenTTS, OpenAI/OpenAI-compatible TTS, and ElevenLabs-style TTS adapters, including assertions that configured credential values are not emitted in TUI status/details or persisted config. Exact-head CI passed in run `36177527935`, PR #425 merged as `07d002a0ad07c36fb913e150000e030bee316163`, and the final reconciled master state for the same head landed as PR #426 `8c8d6158a03327f6b8e925a1fbb38417fb10c171` with merged-master CI run `36178707377`.

---

# R8 — Acceptance and fresh-machine qualification

## PCG-070 — Strengthen production-composition integration tests

- [ ] Configure fake LLM/TTS providers through durable provider configuration.
- [ ] Prove production generation calls those configured providers.
- [ ] Prove generated turns/audio contain provider-supplied unique markers.
- [ ] Prove missing providers fail before output is produced.
- [ ] Prove export contains provider-backed transcript/audio artifacts.

## PCG-071 — Strengthen CLI acceptance workflow

- [ ] Configure deterministic providers through normal CLI/user configuration paths.
- [ ] Run preflight-equivalent readiness checks before generation.
- [ ] Generate to completion through the shared start service.
- [ ] Assert provider-backed turns, provider-backed TTS artifacts, transcript export, metadata, manifest, and audio output.
- [ ] Exercise duplicate-safe generation start and one pause/resume path.

## PCG-072 — Strengthen TUI acceptance workflow

- [ ] Configure/select deterministic providers through production TUI/controller paths.
- [ ] Build plan and pass preflight.
- [ ] Click Generate and enter monitor through the shared start service.
- [ ] Complete provider-backed generation.
- [ ] Open transcript review and Episode Library export.
- [ ] Assert provider-backed transcript/audio artifacts and duplicate-click safety.

## PCG-073 — Strengthen installed-wheel fresh-machine gate

- [ ] Build wheel from exact head and install into a clean Python 3.12 environment.
- [ ] Launch installed CLI and TUI entry points.
- [ ] Configure deterministic providers through installed production paths.
- [ ] Generate provider-backed transcript/audio without source-tree imports.
- [ ] Export transcript, metadata, manifest, and audio.
- [ ] Keep real KittenTTS CPU smoke as a separate bounded qualification.
- [ ] Keep normal CI free of paid credentials and live external-service requirements.

---

# R9 — Documentation and compatibility

## PCG-080 — Update user documentation

- [ ] Document provider-backed production generation behavior.
- [ ] Document deterministic CI/development providers separately from production adapters.
- [ ] Document CLI/TUI preflight and generation-start parity.
- [ ] Document duplicate-run behavior.
- [ ] Document TTS provider, voice, and audio artifact behavior.
- [ ] Document export semantics and pipeline stage semantics.

## PCG-081 — Update developer architecture documentation

- [ ] Document the shared generation start service.
- [ ] Document provider-backed generation stage contracts.
- [ ] Document provider-backed TTS stage contracts.
- [ ] Document stage boundary semantics and export semantics.
- [ ] Document TTS artifact status canonicalization and migration behavior.
- [ ] Document deterministic provider-boundary testing strategy.

## PCG-082 — Persisted-data compatibility

- [ ] Test existing provider configuration records still load.
- [ ] Test existing episodes/runs/transcripts/audio artifacts still load.
- [ ] Add migration/normalization for TTS artifact statuses if needed.
- [ ] Reject ambiguous legacy provider/TTS entries with actionable guidance where automatic migration is unsafe.

---

# R10 — Final qualification and reconciliation

## PCG-090 — Full qualification

- [ ] Full test suite passes.
- [ ] Formatter passes.
- [ ] Ruff passes.
- [ ] mypy passes.
- [ ] Build succeeds.
- [ ] Provider-backed production-composition integration suite passes.
- [ ] CLI provider-backed acceptance workflow passes.
- [ ] TUI provider-backed acceptance workflow passes.
- [ ] Installed-wheel provider-backed fresh-machine gate passes.
- [ ] Duplicate-run matrix passes.
- [ ] Fail-fast readiness matrix passes.
- [ ] TTS artifact status compatibility matrix passes.
- [ ] Provider UI/configuration matrix passes.
- [ ] Security/redaction regressions remain green.
- [ ] Real KittenTTS CPU smoke remains green.
- [ ] No normal-CI dependency on paid credentials/live external services.

## PCG-091 — TODO reconciliation

- [ ] Every task and subtask above has implementation evidence.
- [ ] Every acceptance criterion in the spec has test or documentation evidence.
- [ ] No hidden deterministic production shortcut remains outside explicit configured test/development provider adapters.
- [ ] Exact remediation-head CI passes.
- [ ] Remediation PR merges to `master`.
- [ ] Reload this TODO from merged `master`.
- [ ] Exact merged-master CI passes.
- [ ] Only then mark production generation correctness remediation complete.
