# Deeper Dive Production Generation Post-Review Remediation TODO

**Created:** 2026-09-27  
**Status:** In implementation  
**Authority:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_SPEC_2026-09-27.md`  
**Predecessor:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_FOLLOWUP_TODO_2026-09-25.md`

This checklist is the source of completion truth for the post-review remediation. A checkbox requires production wiring, focused regression evidence, exact-head CI, and reconciliation on `master`.

---

## Execution rules

- [ ] Reload this TODO and companion spec from current `master` at the start of every run and after every successful merge/direct-master write.
- [ ] Inspect current `master`, relevant Ralph branches/open PRs, and CI before implementing duplicate work.
- [ ] Do not rewrite the previous completed follow-up TODO to hide review findings.
- [ ] Prefer direct `master` work when Ralph Bridge policy permits; if policy requires a branch/PR, batch coherent clusters rather than one PR per checkbox.
- [ ] Route CLI/TUI/background/repair behavior through shared production services.
- [ ] Keep deterministic fake providers behind the same provider config/factory/registry boundaries as real providers.
- [ ] Do not mark a task complete because a class/function exists; prove the end-to-end production behavior.
- [ ] Keep compatibility with existing persisted data unless an explicit tested migration is required.

---

# R1 — Multi-turn/multi-segment production conversation

## PRR-100 — Replace one-turn conversation generation

- [x] Inventory current conversation-stage durable state and checkpoints.
- [x] Introduce a public conversation-generation service.
- [x] Load ordered durable plan segments.
- [x] Load/resume `ConversationState`.
- [x] Generate successive turns until completion rather than exactly one turn.
- [x] Stop treating any existing turn as stage completion.
- [x] Persist each turn + evidence + provider/model identity + state + checkpoint atomically.
- [x] Resume from first incomplete unit after interruption.
- [x] Add partial-run resume regression proving no duplicate turns.

## PRR-101 — Segment/episode completion

- [x] Honor `CONTINUE`.
- [x] Honor `COMPLETE_SEGMENT` and persist segment advancement.
- [x] Honor `COMPLETE_EPISODE`.
- [x] Define bounded fallback behavior when directing is unassigned.
- [x] Keep speakers restricted to participating episode hosts.
- [x] Keep evidence restricted to the current episode evidence scope.
- [x] Add deterministic completion-signal matrix tests.

## PRR-102 — Safety and duration bounds

- [x] Define maximum turns per segment.
- [x] Define maximum turns per episode.
- [x] Integrate target word/duration budgeting.
- [x] Define behavior for a provider that never completes.
- [x] Define early-completion behavior.
- [x] Add non-completing-provider safety test.
- [x] Add multi-host/multi-segment acceptance producing multiple durable turns.

---

# R2 — Transactional provider config/runtime

## PRR-110 — Transactional save/edit

- [x] Build candidate config in memory before persistence.
- [x] Validate candidate `ProviderConfig`.
- [x] Build complete candidate `ProviderBuildResult`.
- [x] Persist only after runtime build succeeds.
- [x] Publish runtime only after persistence succeeds.
- [x] Preserve prior durable config on failure.
- [x] Preserve prior live runtime on failure.
- [x] Test missing credential-env rollback.
- [x] Test missing base URL/voice catalog rollback.
- [x] Test unsupported/invalid adapter rollback.
- [x] Prove failed save cannot break next startup.

## PRR-111 — Transactional provider removal

- [x] Build/validate remaining candidate config before persisting removal.
- [x] Preserve previous durable/runtime state on failure.
- [x] Add successful removal test.
- [x] Add failed removal rollback test.
- [x] Prove removed provider cannot remain usable from stale registries.

## PRR-112 — One provider-runtime owner

- [x] Define a typed authoritative provider-runtime owner/accessor.
- [x] Remove stale snapshots between controller and composition.
- [x] Refresh planning/directing/host-generation/verification/TTS/repair/preflight/health together.
- [x] Fix injected/custom TUI controller synchronization.
- [x] Add same-session injected-controller acceptance.
- [x] Add same-session provider edit proving new identity is used without restart.

## PRR-113 — One locality/network-scope policy

- [x] Centralize local/remote classification.
- [x] Use it in `GenerationStartService`.
- [x] Use it in TUI preflight.
- [x] Use it in routing/security display.
- [x] Explicit local override wins.
- [x] Explicit remote override wins.
- [x] Add matrix covering fake, fake-tts, kitten, Ollama, llama-server, OpenAI, OpenAI TTS, compatible TTS, ElevenLabs, overrides.

---

# R3 — Complete preflight and durable failures

## PRR-120 — Validate every executed model role

- [x] Replace incomplete hard-coded role selection.
- [x] Require `episode_planning` when no valid plan exists.
- [x] Require `host_generation` when conversation work remains.
- [x] Validate configured `directing`.
- [x] Validate configured `verification`.
- [x] Keep resolver extensible to future research/source roles.
- [x] Negative test: unknown directing provider.
- [x] Negative test: unavailable directing model.
- [x] Negative test: unhealthy directing provider.
- [x] Equivalent verification-role negatives.
- [x] Prove blockers occur before expensive generation/run creation where applicable.

## PRR-121 — Preflight/production parity

- [x] Provider existence parity.
- [x] Model availability parity.
- [x] Voice availability parity.
- [x] Network/local-only parity.
- [x] Provider-health parity.
- [x] Reuse one table-driven routing/preflight matrix across CLI/TUI tests.

## PRR-122 — Durable post-run failure boundary

- [x] Inventory execution-time checks that can currently escape before orchestrator failure persistence.
- [x] Move/wrap them inside a durable run execution boundary.
- [x] Persist failed state/stage/code/sanitized message/timestamp.
- [x] Prevent stale `pending` or `running` state after execution failure.
- [x] Regression: create run → invalidate assignment → execute → durable failed.
- [x] Verify no downstream checkpoint after failure.

---

# R4 — Plan validity and evidence integrity

## PRR-130 — Shared valid-plan policy

- [x] Require plan row belonging to episode.
- [x] Require at least one segment.
- [x] Validate persisted JSON.
- [x] Validate coherent ordinals.
- [x] Validate non-empty titles.
- [x] Validate positive durations.
- [x] Validate lead-host membership.
- [x] Validate evidence scope.
- [x] Define allowed plan statuses for generation.
- [x] Make planning skip only valid usable plans.
- [x] Make generation-start role derivation use same validity result.
- [x] Test empty/corrupt/invalid/disallowed plans.

## PRR-131 — Fix evidence-validation semantics

- [x] Replace “empty set disables validation” behavior.
- [x] Make disabled/unavailable validation explicit.
- [x] Make active empty scope reject all evidence IDs.
- [x] Validate `regenerate_segment()`.
- [x] Validate `edit_segment()`.
- [x] Reject nonexistent evidence IDs.
- [x] Reject cross-project evidence IDs.
- [x] Preserve valid evidence IDs.

---

# R5 — Security/redaction

## PRR-140 — Canonical recursive sanitizer

- [x] One sanitizer API for all durable/user-visible output.
- [x] Cover authorization/API-key variants/token/access-token/refresh-token/secret/client-secret/password/cookie keys.
- [x] Preserve Bearer redaction.
- [x] Preserve assignment redaction.
- [x] Preserve quoted-map redaction.
- [x] Preserve credential-URL redaction.
- [x] Preserve nested collection redaction.
- [x] Preserve exception cause/context sanitization.
- [x] Add non-secret false-positive tests.

## PRR-141 — Export metadata uses canonical sanitizer

- [x] Remove bespoke `EpisodeExporter.write_metadata()` secret vocabulary.
- [x] Recursively sanitize before serialization.
- [x] Test nested `access_token`.
- [x] Test nested `refresh_token`.
- [x] Test `client_secret`.
- [x] Test cookie/authorization.
- [x] Test URL credentials/Bearer strings.
- [x] Preserve normal provenance/identity metadata.

## PRR-142 — Provider-originated UI/status sanitization

- [x] Audit health/model/voice/provider messages to CLI/TUI/preflight.
- [x] Sanitize before presentation/persistence.
- [x] Health-message synthetic-secret regression.
- [x] Discovery-exception synthetic-secret regression.
- [x] Verify `[REDACTED]` is shown and secret is absent.

## PRR-143 — Credential non-persistence matrix

- [x] Provider config stores references, not values.
- [x] Failed provider save stores no values.
- [x] Structured diagnostics store no values.
- [x] Run failures store no values.
- [x] Export metadata stores no values.
- [x] CLI/TUI status stores/displays no values.
- [x] Add representative end-to-end security matrix.

---

# R6 — TTS/composition correctness

## PRR-150 — Resolve MP3/WAV incompatibility before expensive work

- [x] Choose WAV-only preflight or supported multi-format composition policy.
- [x] Implement the chosen policy.
- [x] Make CLI/TUI behavior identical.
- [x] Test OpenAI-compatible TTS configured for MP3.
- [x] Prove unsupported configuration does not invoke expensive TTS synthesis.
- [x] Preserve Kitten WAV-only contract.

## PRR-151 — Validate full returned TTS identity

- [x] Validate provider.
- [x] Validate voice.
- [x] Validate explicitly requested model.
- [x] Define adapter behavior when model identity cannot be reported.
- [x] Validate persisted format/path extension.
- [x] Do not save success on identity mismatch.
- [x] Add mismatched-model regression.
- [x] Add positive model-identity coverage.

## PRR-152 — Production-quality resampling

- [ ] Select FFmpeg/libswresample or another appropriate deterministic resampler.
- [ ] Route production normalization through it.
- [ ] Preserve canonical 24 kHz mono signed-16-bit contract unless intentionally revised.
- [ ] Preserve actionable unreadable/unsupported failures.
- [ ] Add 12 kHz stereo conversion test.
- [ ] Add second nontrivial rate conversion test.
- [ ] Avoid exact PCM assertions that vary by runtime version.
- [ ] Document dependency/fresh-machine coverage.

## PRR-153 — Public FFmpeg API

- [ ] Stop calling `FFmpegComposer._run()` externally.
- [ ] Add public transcode/conversion API or audio export service.
- [ ] Test command/error behavior through public API.
- [ ] Keep FFmpeg errors sanitized/actionable.

---

# R7 — Transcript repair and TTS cache lifecycle

## PRR-160 — Real production repair recheck/update

- [ ] Remove production `_NoOpRepairRechecker`.
- [ ] Remove production `_NoOpSummaryUpdater`.
- [ ] Route repaired text through real claim extraction/verification/recheck.
- [ ] Update conversation summary/context where required.
- [ ] Preserve unaffected turns.
- [ ] Regression proving stale claims are replaced/reverified.
- [ ] Regression proving required summary/context update.

## PRR-161 — Public audio regeneration after repair

- [ ] Remove imports/calls of private `_tts_stage` and `_composition_stage` from review code.
- [ ] Add public service operation for affected TTS + episode audio regeneration.
- [ ] Use shared provider runtime.
- [ ] Preserve timeline/playback identity.
- [ ] Sanitize repair provider/runtime failures.
- [ ] TUI/controller repair → audio → timeline → export regression.

## PRR-162 — Reference-aware physical cache cleanup

- [ ] Define cleanup policy.
- [ ] Preserve physical artifact still referenced by another turn.
- [ ] Delete/collect unreferenced obsolete artifact.
- [ ] Preserve active artifact files.
- [ ] Duplicate-cache repair regression.
- [ ] Unique-cache repair regression.
- [ ] Repeated-repair no-unbounded-orphan regression.

---

# R8 — Explicit composition architecture and style

## PRR-170 — Remove hidden composition service-locator state

- [ ] Make production composition/application context explicit and typed.
- [ ] Inject it into controllers that need it.
- [ ] Remove production `getattr(service, "_production_composition", ...)`.
- [ ] Remove test/TUI reach-through `app.service._production_composition`.
- [ ] Remove obsolete `type: ignore[attr-defined]`.
- [ ] Test normal app construction.
- [ ] Test injected service/controller construction.
- [ ] Prove CLI/TUI still share production services.

## PRR-171 — Public service boundaries

- [ ] Replace cross-module private stage calls with public operations.
- [ ] Keep stage handlers thin adapters around public services where practical.
- [ ] Prefer public service tests over private-function contract tests.

## PRR-172 — Style suppression cleanup

- [ ] Audit touched `# fmt: off/on`.
- [ ] Remove avoidable formatter suppressions.
- [ ] Audit touched broad Ruff import-order suppressions.
- [ ] Remove avoidable suppressions.
- [ ] Run formatter/lint after cleanup.
- [ ] Avoid unrelated style churn.

## PRR-173 — Consolidate duplicated raw SQL where useful

- [ ] Inventory transcript/claim/source-passage raw SQL overlapping repository/service responsibilities.
- [ ] Consolidate repeated production reads where it reduces drift.
- [ ] Keep compatibility-specific direct SQL when it clearly serves legacy-state testing.
- [ ] Add regressions around consolidated paths.

---

# R9 — Shared acceptance fixture

## PRR-180 — Build fixture through public production services

- [ ] Configure providers through durable config/factory.
- [ ] Create/index corpus through production source/corpus APIs where practical.
- [ ] Create hosts through public host APIs.
- [ ] Create episode through public episode APIs.
- [ ] Build plan through `EpisodePlannerService`/public plan entry point.
- [ ] Remove direct normal-acceptance `save_plan()` seeding.
- [ ] Generate through shared generation-start/pipeline.
- [ ] Produce multiple turns when plan requires them.
- [ ] Generate TTS/timeline/audio through production services.
- [ ] Export through shared export service.

## PRR-181 — Reuse fixture family

- [ ] CLI plan/generate/status/export.
- [ ] TUI provider save/reload/preflight/generate/monitor/review/library/export.
- [ ] Duplicate start/pause/resume/cancel.
- [ ] Multi-episode isolation.
- [ ] Evidence/provenance.
- [ ] TTS cache/artifact identity.
- [ ] Installed-wheel workflow where practical.
- [ ] Remove redundant one-off setup that no longer provides independent coverage.

## PRR-182 — True auto-planning acceptance

- [ ] CLI `episode generate` starts without a persisted plan.
- [ ] Prove configured `episode_planning` provider/model is invoked.
- [ ] Prove plan is persisted.
- [ ] Prove conversation consumes the generated plan.
- [ ] Prove TUI shares the same boundary.
- [ ] Negative auto-planning-output acceptance.

## PRR-183 — Multi-episode isolation with fixture family

- [ ] Two episodes in one project.
- [ ] No turn crossover.
- [ ] No evidence/source-passage crossover.
- [ ] No TTS/timeline crossover.
- [ ] Playback resolves selected episode only.
- [ ] Review export isolation.
- [ ] Episode Library export isolation.
- [ ] Filename/metadata run+episode identity isolation.

---

# R10 — CI/fresh-machine policy

## PRR-190 — External Kitten qualification policy

- [ ] Decide mandatory external-network gate vs separate opt-in/scheduled gate.
- [ ] Document decision in workflow/developer docs.
- [ ] If mandatory, explicitly state fresh-machine CI downloads external runtime assets.
- [ ] If separate, retain deterministic mandatory fake/local TTS coverage.
- [ ] Do not claim mandatory CI has no external dependency when it does.
- [ ] Keep paid credentials/cloud calls out of mandatory deterministic tests.

## PRR-191 — Installed-wheel fresh-machine gate

- [ ] Build wheel from exact remediation head.
- [ ] Install into clean environment.
- [ ] Launch installed CLI.
- [ ] Launch installed TUI.
- [ ] Exercise project/source/host/episode path.
- [ ] Exercise planning/auto-planning through installed code.
- [ ] Exercise generation.
- [ ] Exercise export.
- [ ] Validate non-empty transcript/manifest/metadata/audio.
- [ ] Validate installed sanitizer behavior.
- [ ] Record exact CI evidence.

---

# R11 — Documentation and compatibility

## PRR-200 — Documentation

- [ ] Document multi-turn/multi-segment generation.
- [ ] Document completion signals/safety bounds.
- [ ] Document transactional provider save/remove rollback.
- [ ] Document exact role preflight policy.
- [ ] Document valid-plan policy.
- [ ] Document plan evidence edit/regeneration validation.
- [ ] Document TTS/composition format policy.
- [ ] Document canonical redaction/export guarantees.
- [ ] Document repair reverification/audio regeneration.
- [ ] Document cache cleanup.
- [ ] Document explicit composition ownership.
- [ ] Document Kitten qualification policy.

## PRR-201 — Persisted compatibility matrix

- [ ] Current provider config loads.
- [ ] Legacy TTS `completed` remains readable/normalizable.
- [ ] Existing episodes/runs/turns/provider-identity rows load.
- [ ] Existing timelines load.
- [ ] Existing exports remain readable.
- [ ] Add migration only if required.
- [ ] If migration exists, prove idempotent/failure-safe behavior.

---

# R12 — Qualification

## PRR-210 — Static/quality gates

- [ ] `uv lock --check`
- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy`
- [ ] `uv run pytest`
- [ ] `uv build`
- [ ] CLI/import smoke

## PRR-211 — Focused regression matrices

- [x] Multi-turn/multi-segment generation.
- [ ] Pause/resume/cancel/resume-after-failure.
- [x] Provider transaction rollback.
- [x] Provider runtime coherence.
- [x] Local/remote route matrix.
- [x] Directing/verification preflight matrix.
- [x] Valid/corrupt plan matrix.
- [x] Plan evidence edit/regeneration isolation.
- [x] Security/redaction.
- [x] TTS format/composition compatibility.
- [x] TTS returned identity.
- [ ] Cache invalidation/orphan cleanup.
- [ ] Transcript repair/reverification/regeneration.
- [ ] CLI acceptance.
- [ ] TUI acceptance.
- [ ] Multi-episode isolation.
- [ ] Installed-wheel fresh-machine.
- [ ] Chosen real-Kitten qualification.

---

# R13 — Final reconciliation

## PRR-220 — Reconcile implementation evidence

- [ ] Record implementation commit SHA(s) for R1–R12.
- [ ] Record PR number(s) only where Ralph Bridge policy required them.
- [ ] Record focused test names per cluster.
- [ ] Record exact-head CI run ID/conclusion.
- [ ] Confirm every checked item is production behavior, not only fixture behavior.
- [ ] Confirm every issue in the companion spec is addressed.
- [ ] Confirm zero unchecked items before declaring remediation complete.

## PRR-221 — Final current-`master` qualification

- [ ] Completed remediation and reconciled TODO are on `master`.
- [ ] Reload this TODO from current `master`.
- [ ] Reload companion spec from current `master`.
- [ ] Confirm zero unchecked tasks.
- [ ] Observe exact current-`master` CI.
- [ ] Quality job passes.
- [ ] Fresh-machine installed-wheel gate passes.
- [ ] Chosen Kitten qualification gate passes.
- [ ] Record current/final `master` SHA.
- [ ] Record final CI run ID/conclusion.
- [ ] Only then mark remediation complete.

---

## Closeout evidence

Populate during implementation; do not pre-check.

- Implementation head SHA: R1/R2 foundation merged via `8976210f23a5b6035063cc65a3902c93d0865ed5` (PR #467, head `aa15e956e6f0d5b5f6fc79358eb54c032e0b0085`); remaining PRR-110 provider rollback coverage merged via `226c20c7bc58f72fbc7da4ac4e9656921cd86068` (PR #468, head `7e3325d332134ecd2077d28f56ffef9b856ba4e4`); PRR-112 provider runtime ownership merged via `d4ca66af9ee4a8e0d59ad66c7b18af9c6bc5f383` (PR #470, head `82729af3162b723176b39b21f14788d2c3ee221e`); PRR-113 locality/network-scope policy merged via `9fe2a03ba2f243aed083e42f1cac26b48e6f2761` (PR #473, head `ea532e2f9e632646535712b5d09c7acb30a0a2e9`); PRR-120 role-preflight/role-derivation work merged via `89bd15523611ca90257fdacaea85e1ee47e6df20` (PR #475), `561d31427f02e8c1973ac72f76143c4725569c2b` (PR #476), `725b1e4483a7b88c94b6cae95694ca4f3783443e` (PR #477), and direct-master commits `1136a1138f5cabedb4febdb9ee9c3caa7ab39d54` / `de5ee9cc3bbabedfe86b378a7876f81e19c3502f`; PRR-122 durable failure boundary merged via direct-master commits `f004da1f6c516bcfba8553a45b991856dc19a80f` / `72c12f4d14ff4be7634af694a8a88df3b56d3bf3`; PRR-151 returned TTS identity and persisted format validation merged via direct-master commits `0b374c613c5477733794d7808a410d661824b4b9`, `cb90dec43921d71fe00dad414d16fe9c202720f0`, and `ab16efc50347c1e5c221e48cc602328a2cf52cba`; PRR-150 WAV-only TTS composition preflight merged via direct-master commits `4ddc04130f50f0dd2d8c5ef6dadb69589506ff4e`, `4a99e885e24d438b4a744450ea4cd2a089f79d97`, and `b511c92d0eec2fe3f8edf6f08f4a01e048c6aa9f`.
- Exact-head CI run: `36345119231` on `8976210f23a5b6035063cc65a3902c93d0865ed5`, conclusion `success`; `36345978069` on `226c20c7bc58f72fbc7da4ac4e9656921cd86068`, conclusion `success`; `36346718464` on `d4ca66af9ee4a8e0d59ad66c7b18af9c6bc5f383`, conclusion `success`; `36347992192` on `9fe2a03ba2f243aed083e42f1cac26b48e6f2761`, conclusion `success`; `36349695698` on `89bd15523611ca90257fdacaea85e1ee47e6df20`, conclusion `success`; `36349972095` on `561d31427f02e8c1973ac72f76143c4725569c2b`, conclusion `success`; `36371811648` on `725b1e4483a7b88c94b6cae95694ca4f3783443e`, conclusion `success`; `36372724055` on `de5ee9cc3bbabedfe86b378a7876f81e19c3502f`, conclusion `success`; `36373152115` on `72c12f4d14ff4be7634af694a8a88df3b56d3bf3`, conclusion `success`; `36393651173` on `ab16efc50347c1e5c221e48cc602328a2cf52cba`, conclusion `success`; `36397350910` on `b511c92d0eec2fe3f8edf6f08f4a01e048c6aa9f`, conclusion `success`.
- Current/final `master` SHA:
- Current/final `master` CI run:
- Relevant PRs if policy required: #467 for R1 and R2 transactional-provider foundation; #468 for remaining PRR-110 provider rollback regressions; #470 for PRR-112 provider runtime ownership/coherence; #473 for PRR-113 shared locality/network-scope policy; #475/#476/#477 for PRR-120 role-preflight evidence.
- Multi-turn generation tests: `tests/test_conversation_generation.py::test_multi_segment_generation_honors_completion_signals_atomically`, `tests/test_conversation_generation.py::test_conversation_resume_after_failure_does_not_duplicate_prior_turn`, `tests/test_conversation_generation.py::test_non_completing_director_is_bounded_per_segment`, `tests/test_conversation_generation.py::test_episode_turn_safety_bound_fails_predictably`; `tests/test_followup_acceptance_fixture.py` updated to expect multiple conversation turns.
- Provider transaction/runtime tests: `tests/test_provider_transactions.py::test_failed_provider_save_preserves_durable_config_and_live_runtime`, `tests/test_provider_transactions.py::test_successful_provider_save_publishes_built_candidate_after_persistence`, `tests/test_provider_transactions.py::test_missing_credential_env_provider_save_rolls_back_config_and_runtime`, `tests/test_provider_transactions.py::test_missing_tts_base_url_or_voice_catalog_rolls_back_config_and_runtime`, `tests/test_provider_transactions.py::test_unsupported_provider_adapter_save_rolls_back_without_building`, `tests/test_provider_transactions.py::test_failed_provider_save_cannot_break_next_startup`, `tests/test_provider_transactions.py::test_failed_provider_removal_preserves_durable_config_and_live_runtime`, `tests/test_provider_transactions.py::test_successful_provider_removal_drops_provider_from_live_runtime`, `tests/test_composition.py::test_provider_runtime_refresh_updates_same_session_consumers`, `tests/test_composition.py::test_injected_provider_controller_refreshes_composition_consumers`, `tests/test_composition.py::test_production_composition_loads_persisted_providers`, `tests/test_network_scope.py::test_provider_network_policy_default_scope_matrix`, `tests/test_network_scope.py::test_explicit_network_scope_overrides_adapter_default`, `tests/test_network_scope.py::test_local_provider_ids_respect_defaults_and_explicit_remote_override`, `tests/test_network_scope.py::test_provider_factory_uses_shared_network_scope_policy`.
- Preflight/durable-failure tests: `tests/test_preflight_model_roles.py::test_unknown_directing_provider_blocks`, `tests/test_preflight_model_roles.py::test_unavailable_verification_model_blocks`, `tests/test_preflight_model_roles.py::test_unhealthy_directing_provider_blocks`, `tests/test_preflight_model_roles.py::test_unknown_verification_provider_blocks`, `tests/test_preflight_model_roles.py::test_unhealthy_verification_provider_blocks`, `tests/test_generation_start.py::test_generation_start_requires_configured_execution_roles`, `tests/test_generation_start.py::test_generation_start_preflight_blocks_before_run_creation`, `tests/test_generation_roles.py::test_required_generation_roles_follow_plan_conversation_and_configured_roles`, `tests/test_generation_roles.py::test_required_generation_roles_are_extensible_and_deduplicated`, `tests/test_generation_start.py::test_generation_start_treats_invalid_persisted_plan_as_missing`, `tests/test_generation_start.py::test_generation_start_omits_host_generation_after_completed_conversation`, `tests/test_durable_generation_failure.py::test_run_generation_persists_assignment_failure_after_run_creation`.
- Plan/evidence tests: `tests/test_plan_validity.py` persisted valid/corrupt/disallowed-plan matrix; `tests/test_episode_planner.py` targeted edit/regeneration evidence-scope matrix; exact-head CI `36380466538` on `09d940446fc71879bb975801a7e59a718505bfa2`.
- Security/redaction tests: `tests/test_recursive_redaction.py` covers canonical recursive sanitizer variants, Bearer/assignment/quoted-map/credential-URL/nested collection redaction, exception cause/context sanitization, non-secret false-positive preservation, and export metadata sanitization; `tests/test_preflight_model_roles.py` covers provider health and model-discovery exception redaction before CLI/TUI preflight/status presentation; `tests/test_security_non_persistence.py` covers provider credential-reference storage, structured diagnostics, run failure persistence, and export metadata non-persistence; exact-head CI `36387686979` on `e19828bb6374ee2a203dbea15df17e82e844439e`, conclusion `success`.
- TTS/audio/cache tests: `tests/test_preflight.py::test_preflight_blocks_openai_compatible_mp3_before_synthesis`, `tests/test_preflight.py::test_preflight_preserves_kitten_wav_only_composition_contract`, `tests/test_tts_identity_validation.py::test_tts_stage_rejects_mismatched_returned_model_without_saving`, `tests/test_tts_identity_validation.py::test_tts_stage_rejects_unreported_requested_model_without_saving`, `tests/test_tts_identity_validation.py::test_tts_stage_persists_positive_model_identity_and_format`, `tests/test_tts_identity_validation.py::test_tts_stage_rejects_invalid_reported_format_without_saving`; exact-head CI `36393651173` on `ab16efc50347c1e5c221e48cc602328a2cf52cba`, conclusion `success`; exact-head CI `36397350910` on `b511c92d0eec2fe3f8edf6f08f4a01e048c6aa9f`, conclusion `success`.
- Transcript-repair tests:
- CLI acceptance:
- TUI acceptance:
- Multi-episode acceptance:
- Installed-wheel gate:
- Kitten qualification policy/evidence:
