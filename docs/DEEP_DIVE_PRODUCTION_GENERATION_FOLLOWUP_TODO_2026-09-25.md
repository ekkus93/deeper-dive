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

- [x] Identify every runtime provider registry consumed by preflight, planning, conversation generation, TTS generation, provider health, and export/composition.
- [x] Add a single refresh/access boundary so provider saves/removes update all production runtime consumers in the same process.
- [x] Ensure `ProductionComposition.providers`, `ProviderController`, `PreflightService`, and TTS/LLM registries cannot diverge after provider save/reload.
- [x] Preserve credential non-persistence and credential redaction in TUI status, diagnostics, logs, CLI output, metadata, and exports.
- [x] Add a same-session regression that saves a provider through the TUI/controller and immediately runs preflight/generation/export without restarting.

## PCG-FU-002 — Align preflight and generation provider resolution

- [x] Prove preflight and generation agree on unknown providers, unavailable models, unhealthy providers, TTS voice catalogs, and local/remote network scope.
- [x] Add a regression where preflight passes only if generation can use the same freshly reloaded LLM/TTS providers.
- [x] Add a regression where preflight blocks a provider removed in the same session and generation cannot continue with stale providers.
- [x] Ensure provider refresh behavior works for both CLI-created compositions and TUI app compositions.

**Evidence:** PR #442 added `ProductionComposition.attach_provider_controller()` and `refresh_providers()` as a single runtime refresh boundary, wired `ProviderController.reload()` callbacks into both default composition construction and injected TUI provider-controller attachment, and refreshes `ProductionComposition.providers`, the controller LLM/TTS registries, and `PreflightService` together. `tests/test_followup_provider_runtime.py` proves same-session provider saves make freshly configured LLM/TTS providers visible to preflight and production generation without restart, removed LLM providers block preflight and stale generation, removed TTS providers update the preflight TTS registry, and pipeline LLM-role resolution uses the refreshed production provider registry. Exact-head CI passed for PR #442 in run `36225487822`, PR #442 merged as `70194c681cc36b5604dbd87543445b3df731663e`, and merged-master CI passed in run `36229938457`. Direct-to-master commit `aac80355e6fbe30f907a06bb391652493df2b5b0` extended the same-session provider-save regression so `ProviderController.save_provider()` refreshes provider health, preflight, generation, and Episode Library export in the same process without rebuilding the composition or restarting the app. Exact-head CI for that commit passed in run `36319224669`. Direct-to-master commit `d8302f39d1fe8130187f0115f8880d3f96783d13` added provider-save credential non-persistence coverage proving a credential-backed provider persists the credential environment-variable name but not the secret value; exact-head CI passed in run `36319505379`. Direct-to-master commit `76225372bb09ab481a6b18081d92cb5b1023f9eb` added `docs/PROVIDER_RUNTIME_CONSUMER_INVENTORY_2026-09-27.md`, identifying runtime provider consumers across `ProviderController`, `ProductionComposition.providers`, `PreflightService`, planning, conversation generation, TTS generation, provider health, and export/composition artifact identity; exact-head CI passed in run `36319627872`. Direct-to-master commit `8f329a95cc93d8bb637b423e402a042e86307f0b` fixed explicit `network_scope="remote"` handling in `GenerationStartService._local_provider_ids()` and added PCG-FU-002 matrix coverage for unavailable LLM models, unhealthy LLM providers, and explicit remote-provider/local-only blockers; exact-head CI passed in run `36325524514`. Direct-to-master commit `1465eaad00a3d49c349b88232c6a92c9220ba575` added a CLI-created `ProductionComposition.build()` regression proving persisted provider config is loaded into `ProviderController`, `ProductionComposition.providers`, `PreflightService`, preflight, generation, and transcript output; exact-head CI passed in run `36325718089`. PR #460 repaired the PCG-FU-002 provider-runtime matrix formatting while preserving the TTS voice-catalog mismatch regression; exact-head CI passed in run `36326721450`, PR #460 merged as `18dccbb29952bfa5b73b7be2ef89b3f200673903`, and merged-master CI passed in run `36326844928`. PR #462 added recursive export-metadata redaction coverage in `tests/test_error_redaction_surfaces.py`, while existing redaction-surface tests cover sanitized diagnostics, TUI-visible status, delegated CLI stderr, and nested debug/repr payloads; exact-head CI passed in run `36327377917`, PR #462 merged as `e1967850981061147ec41c4a1055c875c3ed43b7`, and merged-master CI passed in run `36327497046`.

---

# R2 — Planning role correctness and durable failure semantics

## PCG-FU-010 — Route pipeline auto-planning through `episode_planning`

- [x] Replace first-provider/first-model selection in pipeline planning with configured `ModelRole.EPISODE_PLANNING` resolution.
- [x] Use the same user > project > episode override precedence used by CLI `episode plan`.
- [x] Construct the planning provider through the refreshed production provider registry.
- [x] Preserve idempotent skip behavior when a valid plan already exists.
- [x] Add a two-provider regression proving auto-planning uses the configured provider/model, not the sorted-first provider.

## PCG-FU-011 — Fail durably when auto-planning cannot produce a valid plan

- [x] Remove silent `ValueError` swallowing from production planning.
- [x] Fail the durable run with sanitized actionable diagnostics when planning provider output is invalid.
- [x] Fail before conversation/TTS/composition when required planning provider/model assignments are missing or invalid.
- [x] Add tests for invalid planning JSON, empty segments, unknown provider, unavailable model, and provider exception.
- [x] Ensure CLI `episode generate`, TUI Generate, and monitor background generation expose consistent planning failures.

**Evidence:** PR #440 routed production pipeline auto-planning through the configured `episode_planning` model role instead of selecting the sorted-first provider/model, preserved the existing plan skip boundary, removed silent planning `ValueError` swallowing, and added `tests/test_followup_planning_runtime.py` coverage proving configured-provider selection and durable failed-run behavior for invalid provider output. It also updated legacy pipeline, monitor, CLI-control/export, and preflight/generate fixtures to use explicit configured planning providers and valid episode configurations. Exact-head CI passed for PR #440 in run `36218606905`, PR #440 merged as `e13e4c42150817562a5ebdb99d77b1d393263584`, and merged-master CI passed in run `36218734135`. PR #442 then tied pipeline role resolution to the refreshed `ProductionComposition.providers.llm_registry`, preserving injected TUI planning while ensuring durable pipeline planning uses the atomically refreshed production registry. Exact-head CI passed for PR #442 in run `36225487822`, PR #442 merged as `70194c681cc36b5604dbd87543445b3df731663e`, and merged-master CI passed in run `36229938457`. PR #455 added deterministic coverage for invalid planning JSON, empty planning segments, unknown planning provider, unavailable planning model, and planning provider exceptions in `tests/test_followup_planning_runtime.py`, proving planning failures remain durable and stop before downstream stages. Exact-head CI for PR #455 passed in run `36315586676`; PR #455 merged as `e30ae1c5b8b0fca16ad1289b86baccb8b6e0b1fe`; merged-master CI passed in run `36315693207`. PR #458 added deterministic cross-surface coverage for planning failures across CLI `episode generate`, TUI Generate/preflight, and monitor background generation in `tests/test_followup_planning_cross_surface.py`, proving nonzero CLI failure output, TUI-visible planning errors, and durable monitor failed-run diagnostics before conversation/TTS/composition. Exact-head CI for PR #458 passed in run `36317247087`; PR #458 merged as `a530d8466b541f80800011b3f59ac21408d2a7ab`.

---

# R3 — Generated evidence and provenance

## PCG-FU-020 — Supply source/plan evidence IDs to provider-backed generation

- [x] Define the production evidence source for generation, such as plan segment evidence IDs, retrieval results, or another documented service.
- [x] Make valid evidence IDs available to directing decisions when indexed source evidence exists.
- [x] Make valid evidence IDs available to host-turn generation and constrain provider citations to that set.
- [x] Preserve multi-episode and multi-project evidence isolation.
- [x] Add regression coverage showing generated turns include non-empty evidence IDs when the configured provider selects valid evidence.

## PCG-FU-021 — Validate and export generated provenance end to end

- [x] Reject provider-returned evidence IDs outside the supplied evidence scope.
- [x] Persist valid generated evidence IDs on conversation turns.
- [x] Resolve cited source chunks to source passage metadata/text during export.
- [x] Add an end-to-end provider-backed acceptance test proving exported transcript markdown contains generated citations and source passages without manually seeding turn provenance.
- [x] Add a negative test proving cross-episode or cross-project evidence IDs are not accepted.

**Evidence:** PR #447 wires production conversation generation to derive available evidence IDs from the durable episode plan's segment evidence and passes that evidence scope into both the director decision and host-turn generation path. `tests/test_followup_generated_evidence.py::test_provider_backed_generation_uses_plan_evidence_and_exports_source_passages` proves configured provider-backed generation persists non-empty evidence IDs on generated turns and that Episode Library export resolves those citations into transcript source passages from the indexed source chunk. `tests/test_followup_generated_evidence.py::test_generated_turn_rejects_evidence_outside_director_scope` proves generated host turns cannot cite evidence outside the supplied director scope. Exact-head CI for PR #447 passed in run `36313059185`; PR #447 merged as `5a9947b26dd8e30b44ca2ed9970613b66357beea`; merged-master CI passed in run `36313168607`. PR #450 then filters supplied plan evidence against indexed chunks in the current project database before exposing it to production directing/host-turn generation. `tests/test_followup_generated_evidence.py::test_episode_evidence_ids_filter_cross_project_plan_evidence` proves cross-project plan evidence is not supplied and cannot be cited, and `tests/test_followup_generated_evidence.py::test_episode_evidence_ids_do_not_leak_other_episode_plan` proves one episode's plan evidence does not leak into another episode's generated-evidence scope. Exact-head CI for PR #450 passed in run `36314072318`; PR #450 merged as `7bffee9344f4c0f93c8cb91a7aa3a423d0515f24`; merged-master CI passed in run `36314171529`.

---

# R4 — Real audio composition

## PCG-FU-030 — Replace byte concatenation with valid episode audio composition

- [x] Identify all production paths that compose final episode audio from per-turn TTS artifacts.
- [x] Replace container-byte concatenation with a valid composition path for supported WAV artifacts.
- [x] Ensure the final episode `.wav` has one coherent WAV header and combined PCM frames.
- [x] Preserve timeline items, episode identity, turn ordering, host identity, and artifact references.
- [x] Add tests with two valid WAV turn artifacts proving the final episode WAV opens with `wave.open()` and has expected nonzero combined frames.

## PCG-FU-031 — Define compressed/unsupported audio composition behavior

- [x] Decide whether MP3 and other compressed/container artifacts are composed through FFmpeg or rejected before completion.
- [x] If supported, route compressed composition through the existing FFmpeg/audio abstraction and add deterministic tests. (N/A: compressed/container artifacts are rejected before completion for this follow-up.)
- [x] If not supported, fail with sanitized actionable diagnostics before marking composition complete.
- [x] Add tests for missing, empty, unreadable, unsupported, and mismatched TTS artifacts.
- [x] Keep normal CI free of live paid-provider or external-service requirements.

**Evidence:** PR #444 (`698db310d2634b338b6341cdd5626d5a73abb1f9`) replaced production episode-audio byte concatenation with WAV-aware composition in `src/deeper_dive/composition.py`. `_composition_stage()` now resolves per-turn TTS artifacts through the production artifact repository, normalizes supported `.wav` artifacts, preserves timeline entries with episode/turn/host/artifact identity, and writes the final episode file through `EpisodeExporter.write_wav()` so the output has one coherent WAV header and combined PCM frames. `tests/test_followup_audio_composition.py::test_composition_stage_writes_single_valid_wav_from_two_turn_artifacts` proves two valid turn WAV artifacts compose into a single `wave.open()`-readable episode WAV with expected frame count and timeline artifact/turn ordering. PR #444 also records the compressed/container policy by rejecting non-WAV artifacts before completion with sanitized actionable diagnostics rather than byte-concatenating them. PR #445 (`37ce36e04436fb39b126169cb5d07f21b871d325`) completed the artifact-error matrix with deterministic missing, empty, unreadable, unsupported, and mismatched-parameter coverage. Exact-head CI passed for PR #444 in run `36305445325`; merged-master CI passed for PR #444 in run `36306224064`. Exact-head CI passed for PR #445 in run `36307149518`; merged-master CI passed for PR #445 in run `36307257952`. Normal CI uses deterministic fake providers and no paid/live external TTS services for this coverage.

---

# R5 — TTS response-format and artifact identity

## PCG-FU-040 — Honor configured TTS response formats in production synthesis

- [x] Thread provider-configured TTS response format/settings into `TTSTurn` or an equivalent production synthesis request.
- [x] Ensure OpenAI-compatible TTS configured for `mp3` receives `response_format="mp3"` during production generation.
- [x] Ensure artifact file extension and recorded format/provider metadata match the actual provider result.
- [x] Ensure WAV-only providers, including KittenTTS Micro, reject unsupported response formats before claiming success.
- [x] Add regressions for OpenAI-compatible `mp3`, default WAV, and Kitten WAV-only behavior.

## PCG-FU-041 — Clarify and enforce TTS artifact/cache identity semantics

- [x] Document whether `tts_artifacts` is a per-turn table, a cache table, or a combined compatibility table.
- [x] If every turn should have a persisted artifact row, add or migrate the schema/logic needed to represent duplicate cache reuse across multiple turns.
- [x] If `tts_artifacts` remains cache-centric, update downstream code and docs so no path assumes one row per turn. (N/A: it is explicitly a per-turn artifact-reference table.)
- [x] Ensure composition/export can locate the correct artifact for every turn after cache reuse.
- [x] Ensure transcript repair invalidates stale audio when text, provider, voice, model, response format, or synthesis settings change.
- [x] Add tests for duplicate text/voice cache reuse, per-turn lookup behavior, and repair invalidation/regeneration.

**Evidence:** PR #446 threads configured non-default TTS response formats through production `TTSTurn.settings`, proves OpenAI-compatible `mp3` reaches the provider request, preserves implicit default WAV behavior, rejects non-WAV KittenTTS requests before recording success, and records artifact extension/format/provider/voice/model identity from the actual provider result. Schema v8 makes `tts_artifacts` explicitly per-turn while allowing duplicate turns to share cache key, artifact ID, and physical file; `get_by_turn_id()` and duplicate-cache persistence preserve per-turn composition/export lookup. Cache identity covers text, provider, voice, model, response format, and synthesis settings, while targeted-repair coverage proves changed text regenerates without corrupting another turn that shares the old cache artifact. Production-generation, architecture, and provider docs record these semantics. Exact-head CI for PR #446 passed before merge; PR #446 merged as `0ea12d9ad3fa4f88225769e2748f126fd8aabc9b`, and merged-master CI passed in run `36309239056`.

---

# R6 — Cross-surface acceptance and fresh-machine qualification

## PCG-FU-050 — Extend reusable deterministic acceptance fixtures

- [x] Build or extend a reusable fixture that creates project, source corpus, indexed chunks, hosts, provider config, episode config, plan, generation run, provider-backed turns, TTS artifacts, composed audio, and exports.
- [x] Reuse the fixture across CLI, TUI, production-composition, multi-episode isolation, and export tests.
- [x] Include provider markers, evidence markers, voice/format markers, and artifact identity markers in deterministic fake providers.
- [x] Avoid one-off shortcut fixtures that bypass production services.

## PCG-FU-051 — Add CLI/TUI/fresh-machine follow-up gates

- [x] CLI acceptance covers configured planning provider, provider-backed cited transcript, configured TTS response format, valid composed WAV, export, duplicate start, and pause/resume.
- [x] TUI acceptance covers same-session provider save/reload, preflight, generate, monitor, transcript review, Episode Library export, and duplicate-click safety.
- [x] Fresh-machine installed-wheel validation covers the follow-up production path without source-tree imports.
- [x] Security/redaction tests remain green and include newly introduced provider/settings diagnostics.
- [x] No normal-CI path requires paid credentials or live external services.

**Evidence:** PR #453 adds `tests/followup_acceptance_fixture.py`, a reusable deterministic fixture that creates configured fake LLM/TTS providers, a project, indexed source chunk, host with TTS assignment, episode configuration, durable plan, generation run, provider-backed turn, TTS artifact, composed WAV, and Episode Library export output. `tests/test_followup_acceptance_fixture.py::test_reusable_followup_fixture_runs_generation_composition_and_export` reuses the fixture to prove provider/director markers, non-empty evidence marker `chunk-r6`, TTS provider/voice/format/artifact identity, composed WAV readability, and exported citation/source-passage output. `tests/test_followup_acceptance_fixture.py::test_followup_fixture_supports_duplicate_start_pause_resume_and_cli_export` reuses the same fixture for duplicate generation start, pause/resume, CLI status, and CLI export. Exact-head CI for PR #453 passed in run `36315024384`; PR #453 merged as `9eba1141f6e6bd943dbe18ace344c7625e52e8d4`; merged-master CI passed in run `36315130828`, including the fresh-machine installed-wheel job. The normal CI/fresh-machine path uses configured fake providers for production generation and performs no paid-provider or live external-service calls; the existing fresh-machine script also exercises installed-wheel redaction checks and TUI preflight construction. Direct-to-master commit `6ce633a78b817abfed5beda8712fa11285552aec` reused the same fixture across the TUI production composition: same-session provider save/reload, shared preflight, duplicate-safe Generate selection, production generation, monitor snapshot/recent turns, Transcript Review citations/source passages, Episode Library run state, and Episode Library export. Exact-head CI passed in run `36327966961`. Direct-to-master commits `71b129095ecc4e6970ef3bce9a48ebbc92e30011` and `55759ac211ef95cb27b49c8f08c80d6b7ac2664f` extended the shared fixture into an explicit CLI generation/status/export acceptance gate covering configured `episode_planning`, provider-backed cited transcript output, configured TTS provider/voice/WAV identity, readable composed WAV export, and deterministic FFmpeg discovery; the existing shared-fixture CLI acceptance also covers duplicate start plus pause/resume. Exact-head CI for `55759ac211ef95cb27b49c8f08c80d6b7ac2664f` passed in run `36328362393`.

---

# R7 — Documentation and reconciliation

## PCG-FU-060 — Update documentation

- [x] Update user documentation for same-session provider changes, planning role behavior, citation/provenance generation, TTS response formats, and audio composition support.
- [x] Update architecture documentation for provider runtime refresh, planning-stage failure semantics, evidence selection, audio composition, and artifact/cache identity.
- [x] Update provider documentation for supported response formats and WAV-only provider limitations.
- [x] Link this follow-up from relevant production generation docs without reopening the completed prior TODO.

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

**Evidence:** Direct-to-master commit `26f61c0fbf96ecf471cb5f3aa63e8ea27fc69f46` updated `docs/V1_USER_WORKFLOWS.md` with user-facing same-session provider refresh semantics, configured `episode_planning` behavior, generated citation/provenance rules, TTS response-format and Kitten WAV-only behavior, per-turn artifact/cache identity, and WAV-only composition support. Direct-to-master commit `44eab6788848201d9782b6429f24ee2a20ddc598` updated `docs/PRODUCTION_GENERATION_ARCHITECTURE.md` with developer-facing provider refresh, planning failure, evidence/provenance, TTS response-format/cache identity, and audio-composition contracts, and linked the follow-up spec from the production architecture doc. Exact-head CI for the documentation head passed in run `36318093772`.
