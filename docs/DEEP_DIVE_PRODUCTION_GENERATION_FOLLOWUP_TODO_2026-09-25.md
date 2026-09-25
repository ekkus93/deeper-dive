# Deeper Dive Production Generation Follow-up TODO

**Spec authority:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_FOLLOWUP_SPEC_2026-09-25.md`  
**Created:** 2026-09-25  
**Purpose:** Fix production-quality issues found after the production-generation correctness remediation was completed.

---

## 0. Execution rules

- [ ] Treat this TODO as the authoritative remediation checklist for this follow-up.
- [ ] Do not reopen or modify `docs/DEEP_DIVE_PRODUCTION_GENERATION_CORRECTNESS_TODO_2026-09-24.md` except to reference this follow-up if needed.
- [ ] Use shared production services and provider registries; do not introduce surface-specific shortcuts.
- [ ] Use deterministic fake providers only as explicit configured provider-boundary adapters in tests and development workflows.
- [ ] Keep CLI, TUI, pipeline, and export behavior aligned through shared services wherever practical.
- [ ] Preserve sanitizer, provenance, checkpoint, run-state, artifact identity, and credential-redaction invariants.
- [ ] Require production wiring, regression tests, exact-head CI, merge to `master`, TODO reconciliation, reload from `master`, and merged-master CI before final completion.

---

# R1 — Provider runtime coherence

## PCG-FU-001 — Make provider runtime state coherent after same-session TUI saves

- [ ] Identify every runtime provider registry consumed by preflight, planning, conversation generation, TTS generation, provider health, and export/composition.
- [ ] Add a single refresh/access boundary so provider saves/removes update all production runtime consumers in the same process.
- [ ] Ensure `ProductionComposition.providers`, `ProviderController`, `PreflightService`, and TTS/LLM registries cannot diverge after provider save/reload.
- [ ] Preserve credential non-persistence and credential redaction in TUI status, diagnostics, logs, CLI output, metadata, and exports.
- [ ] Add a same-session regression that saves a provider through the TUI/controller and immediately runs preflight/generation/export without restarting.

## PCG-FU-002 — Align preflight and generation provider resolution

- [ ] Prove preflight and generation agree on unknown providers, unavailable models, unhealthy providers, TTS voice catalogs, and local/remote network scope.
- [ ] Add a regression where preflight passes only if generation can use the same freshly reloaded LLM/TTS providers.
- [ ] Add a regression where preflight blocks a provider removed in the same session and generation cannot continue with stale providers.
- [ ] Ensure provider refresh behavior works for both CLI-created compositions and TUI app compositions.

**Evidence:** _Pending._

---

# R2 — Planning role correctness and durable failure semantics

## PCG-FU-010 — Route pipeline auto-planning through `episode_planning`

- [ ] Replace first-provider/first-model selection in pipeline planning with configured `ModelRole.EPISODE_PLANNING` resolution.
- [ ] Use the same user > project > episode override precedence used by CLI `episode plan`.
- [ ] Construct the planning provider through the refreshed production provider registry.
- [ ] Preserve idempotent skip behavior when a valid plan already exists.
- [ ] Add a two-provider regression proving auto-planning uses the configured provider/model, not the sorted-first provider.

## PCG-FU-011 — Fail durably when auto-planning cannot produce a valid plan

- [ ] Remove silent `ValueError` swallowing from production planning.
- [ ] Fail the durable run with sanitized actionable diagnostics when planning provider output is invalid.
- [ ] Fail before conversation/TTS/composition when required planning provider/model assignments are missing or invalid.
- [ ] Add tests for invalid planning JSON, empty segments, unknown provider, unavailable model, and provider exception.
- [ ] Ensure CLI `episode generate`, TUI Generate, and monitor background generation expose consistent planning failures.

**Evidence:** _Pending._

---

# R3 — Generated evidence and provenance

## PCG-FU-020 — Supply source/plan evidence IDs to provider-backed generation

- [ ] Define the production evidence source for generation, such as plan segment evidence IDs, retrieval results, or another documented service.
- [ ] Make valid evidence IDs available to directing decisions when indexed source evidence exists.
- [ ] Make valid evidence IDs available to host-turn generation and constrain provider citations to that set.
- [ ] Preserve multi-episode and multi-project evidence isolation.
- [ ] Add regression coverage showing generated turns include non-empty evidence IDs when the configured provider selects valid evidence.

## PCG-FU-021 — Validate and export generated provenance end to end

- [ ] Reject provider-returned evidence IDs outside the supplied evidence scope.
- [ ] Persist valid generated evidence IDs on conversation turns.
- [ ] Resolve cited source chunks to source passage metadata/text during export.
- [ ] Add an end-to-end provider-backed acceptance test proving exported transcript markdown contains generated citations and source passages without manually seeding turn provenance.
- [ ] Add a negative test proving cross-episode or cross-project evidence IDs are not accepted.

**Evidence:** _Pending._

---

# R4 — Real audio composition

## PCG-FU-030 — Replace byte concatenation with valid episode audio composition

- [ ] Identify all production paths that compose final episode audio from per-turn TTS artifacts.
- [ ] Replace container-byte concatenation with a valid composition path for supported WAV artifacts.
- [ ] Ensure the final episode `.wav` has one coherent WAV header and combined PCM frames.
- [ ] Preserve timeline items, episode identity, turn ordering, host identity, and artifact references.
- [ ] Add tests with two valid WAV turn artifacts proving the final episode WAV opens with `wave.open()` and has expected nonzero combined frames.

## PCG-FU-031 — Define compressed/unsupported audio composition behavior

- [ ] Decide whether MP3 and other compressed/container artifacts are composed through FFmpeg or rejected before completion.
- [ ] If supported, route compressed composition through the existing FFmpeg/audio abstraction and add deterministic tests.
- [ ] If not supported, fail with sanitized actionable diagnostics before marking composition complete.
- [ ] Add tests for missing, empty, unreadable, unsupported, and mismatched TTS artifacts.
- [ ] Keep normal CI free of live paid-provider or external-service requirements.

**Evidence:** _Pending._

---

# R5 — TTS response-format and artifact identity

## PCG-FU-040 — Honor configured TTS response formats in production synthesis

- [ ] Thread provider-configured TTS response format/settings into `TTSTurn` or an equivalent production synthesis request.
- [ ] Ensure OpenAI-compatible TTS configured for `mp3` receives `response_format="mp3"` during production generation.
- [ ] Ensure artifact file extension and recorded format/provider metadata match the actual provider result.
- [ ] Ensure WAV-only providers, including KittenTTS Micro, reject unsupported response formats before claiming success.
- [ ] Add regressions for OpenAI-compatible `mp3`, default WAV, and Kitten WAV-only behavior.

## PCG-FU-041 — Clarify and enforce TTS artifact/cache identity semantics

- [ ] Document whether `tts_artifacts` is a per-turn table, a cache table, or a combined compatibility table.
- [ ] If every turn should have a persisted artifact row, add or migrate the schema/logic needed to represent duplicate cache reuse across multiple turns.
- [ ] If `tts_artifacts` remains cache-centric, update downstream code and docs so no path assumes one row per turn.
- [ ] Ensure composition/export can locate the correct artifact for every turn after cache reuse.
- [ ] Ensure transcript repair invalidates stale audio when text, provider, voice, model, response format, or synthesis settings change.
- [ ] Add tests for duplicate text/voice cache reuse, per-turn lookup behavior, and repair invalidation/regeneration.

**Evidence:** _Pending._

---

# R6 — Cross-surface acceptance and fresh-machine qualification

## PCG-FU-050 — Extend reusable deterministic acceptance fixtures

- [ ] Build or extend a reusable fixture that creates project, source corpus, indexed chunks, hosts, provider config, episode config, plan, generation run, provider-backed turns, TTS artifacts, composed audio, and exports.
- [ ] Reuse the fixture across CLI, TUI, production-composition, multi-episode isolation, and export tests.
- [ ] Include provider markers, evidence markers, voice/format markers, and artifact identity markers in deterministic fake providers.
- [ ] Avoid one-off shortcut fixtures that bypass production services.

## PCG-FU-051 — Add CLI/TUI/fresh-machine follow-up gates

- [ ] CLI acceptance covers configured planning provider, provider-backed cited transcript, configured TTS response format, valid composed WAV, export, duplicate start, and pause/resume.
- [ ] TUI acceptance covers same-session provider save/reload, preflight, generate, monitor, transcript review, Episode Library export, and duplicate-click safety.
- [ ] Fresh-machine installed-wheel validation covers the follow-up production path without source-tree imports.
- [ ] Security/redaction tests remain green and include newly introduced provider/settings diagnostics.
- [ ] No normal-CI path requires paid credentials or live external services.

**Evidence:** _Pending._

---

# R7 — Documentation and reconciliation

## PCG-FU-060 — Update documentation

- [ ] Update user documentation for same-session provider changes, planning role behavior, citation/provenance generation, TTS response formats, and audio composition support.
- [ ] Update architecture documentation for provider runtime refresh, planning-stage failure semantics, evidence selection, audio composition, and artifact/cache identity.
- [ ] Update provider documentation for supported response formats and WAV-only provider limitations.
- [ ] Link this follow-up from relevant production generation docs without reopening the completed prior TODO.

## PCG-FU-061 — Final qualification and TODO reconciliation

- [ ] Full test suite passes.
- [ ] Formatter passes.
- [ ] Ruff passes.
- [ ] mypy passes.
- [ ] Build succeeds.
- [ ] Provider runtime coherence regressions pass.
- [ ] Planning role/failure regressions pass.
- [ ] Evidence/provenance generation regressions pass.
- [ ] Real audio composition regressions pass.
- [ ] TTS response-format and artifact identity regressions pass.
- [ ] CLI acceptance passes.
- [ ] TUI acceptance passes.
- [ ] Installed-wheel fresh-machine gate passes.
- [ ] Security/redaction regressions remain green.
- [ ] Exact remediation-head CI passes.
- [ ] Remediation PR merges to `master`.
- [ ] Reload this TODO from merged `master`.
- [ ] Exact merged-master CI passes.
- [ ] Only then mark this follow-up remediation complete.

**Evidence:** _Pending._
