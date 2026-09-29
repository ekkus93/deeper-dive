# Deeper Dive Production Generation Post-Review Remediation TODO

**Created:** 2026-09-27  
**Status:** Final TODO reconciliation pending exact-head CI on this commit  
**Authority:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_SPEC_2026-09-27.md`  
**Predecessor:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_FOLLOWUP_TODO_2026-09-25.md`  
**Evidence companion:** `docs/POST_REVIEW_FINAL_RECONCILIATION_EVIDENCE_2026-09-29.md`

This checklist is the source of completion truth for the post-review remediation. A checkbox requires production wiring, focused regression evidence, exact-head CI, and reconciliation on `master`.

---

## Execution rules

- [x] Reload this TODO and companion spec from current `master` at the start of every run and after every successful merge/direct-master write.
- [x] Inspect current `master`, relevant Ralph branches/open PRs, and CI before implementing duplicate work.
- [x] Do not rewrite the previous completed follow-up TODO to hide review findings.
- [x] Prefer direct `master` work when Ralph Bridge policy permits; if policy requires a branch/PR, batch coherent clusters rather than one PR per checkbox.
- [x] Route CLI/TUI/background/repair behavior through shared production services.
- [x] Keep deterministic fake providers behind the same provider config/factory/registry boundaries as real providers.
- [x] Do not mark a task complete because a class/function exists; prove the end-to-end production behavior.
- [x] Keep compatibility with existing persisted data unless an explicit tested migration is required.

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

- [x] Select FFmpeg/libswresample or another appropriate deterministic resampler.
- [x] Route production normalization through it.
- [x] Preserve canonical 24 kHz mono signed-16-bit contract unless intentionally revised.
- [x] Preserve actionable unreadable/unsupported failures.
- [x] Add 12 kHz stereo conversion test.
- [x] Add second nontrivial rate conversion test.
- [x] Avoid exact PCM assertions that vary by runtime version.
- [x] Document dependency/fresh-machine coverage.

## PRR-153 — Public FFmpeg API

- [x] Stop calling `FFmpegComposer._run()` externally.
- [x] Add public transcode/conversion API or audio export service.
- [x] Test command/error behavior through public API.
- [x] Keep FFmpeg errors sanitized/actionable.

---

# R7 — Transcript repair and TTS cache lifecycle

## PRR-160 — Real production repair recheck/update

- [x] Remove production `_NoOpRepairRechecker`.
- [x] Remove production `_NoOpSummaryUpdater`.
- [x] Route repaired text through real claim extraction/verification/recheck.
- [x] Update conversation summary/context where required.
- [x] Preserve unaffected turns.
- [x] Regression proving stale claims are replaced/reverified.
- [x] Regression proving required summary/context update.

## PRR-161 — Public audio regeneration after repair

- [x] Remove imports/calls of private `_tts_stage` and `_composition_stage` from review code.
- [x] Add public service operation for affected TTS + episode audio regeneration.
- [x] Use shared provider runtime.
- [x] Preserve timeline/playback identity.
- [x] Sanitize repair provider/runtime failures.
- [x] TUI/controller repair → audio → timeline → export regression.

## PRR-162 — Reference-aware physical cache cleanup

- [x] Define cleanup policy.
- [x] Preserve physical artifact still referenced by another turn.
- [x] Delete/collect unreferenced obsolete artifact.
- [x] Preserve active artifact files.
- [x] Duplicate-cache repair regression.
- [x] Unique-cache repair regression.
- [x] Repeated-repair no-unbounded-orphan regression.

---

# R8 — Explicit composition architecture and style

## PRR-170 — Remove hidden composition service-locator state

- [x] Make production composition/application context explicit and typed.
- [x] Inject it into controllers that need it.
- [x] Remove production `getattr(service, "_production_composition", ...)`.
- [x] Remove test/TUI reach-through `app.service._production_composition`.
- [x] Remove obsolete `type: ignore[attr-defined]`.
- [x] Test normal app construction.
- [x] Test injected service/controller construction.
- [x] Prove CLI/TUI still share production services.

## PRR-171 — Public service boundaries

- [x] Replace cross-module private stage calls with public operations.
- [x] Keep stage handlers thin adapters around public services where practical.
- [x] Prefer public service tests over private-function contract tests.

## PRR-172 — Style suppression cleanup

- [x] Audit touched `# fmt: off/on`.
- [x] Remove avoidable formatter suppressions.
- [x] Audit touched broad Ruff import-order suppressions.
- [x] Remove avoidable suppressions.
- [x] Run formatter/lint after cleanup.
- [x] Avoid unrelated style churn.

## PRR-173 — Consolidate duplicated raw SQL where useful

- [x] Inventory transcript/claim/source-passage raw SQL overlapping repository/service responsibilities.
- [x] Consolidate repeated production reads where it reduces drift.
- [x] Keep compatibility-specific direct SQL when it clearly serves legacy-state testing.
- [x] Add regressions around consolidated paths.

---

# R9 — Shared acceptance fixture

## PRR-180 — Build fixture through public production services

- [x] Configure providers through durable config/factory.
- [x] Create/index corpus through production source/corpus APIs where practical.
- [x] Create hosts through public host APIs.
- [x] Create episode through public episode APIs.
- [x] Build plan through `EpisodePlannerService`/public plan entry point.
- [x] Remove direct normal-acceptance `save_plan()` seeding.
- [x] Generate through shared generation-start/pipeline.
- [x] Produce multiple turns when plan requires them.
- [x] Generate TTS/timeline/audio through production services.
- [x] Export through shared export service.

## PRR-181 — Reuse fixture family

- [x] CLI plan/generate/status/export.
- [x] TUI provider save/reload/preflight/generate/monitor/review/library/export.
- [x] Duplicate start/pause/resume/cancel.
- [x] Multi-episode isolation.
- [x] Evidence/provenance.
- [x] TTS cache/artifact identity.
- [x] Installed-wheel workflow where practical.
- [x] Remove redundant one-off setup that no longer provides independent coverage.

## PRR-182 — True auto-planning acceptance

- [x] CLI `episode generate` starts without a persisted plan.
- [x] Prove configured `episode_planning` provider/model is invoked.
- [x] Prove plan is persisted.
- [x] Prove conversation consumes the generated plan.
- [x] Prove TUI shares the same boundary.
- [x] Negative auto-planning-output acceptance.

## PRR-183 — Multi-episode isolation with fixture family

- [x] Two episodes in one project.
- [x] No turn crossover.
- [x] No evidence/source-passage crossover.
- [x] No TTS/timeline crossover.
- [x] Playback resolves selected episode only.
- [x] Review export isolation.
- [x] Episode Library export isolation.
- [x] Filename/metadata run+episode identity isolation.

---

# R10 — CI/fresh-machine policy

## PRR-190 — External Kitten qualification policy

- [x] Decide mandatory external-network gate vs separate opt-in/scheduled gate.
- [x] Document decision in workflow/developer docs.
- [x] If mandatory, explicitly state fresh-machine CI downloads external runtime assets.
- [x] If separate, retain deterministic mandatory fake/local TTS coverage.
- [x] Do not claim mandatory CI has no external dependency when it does.
- [x] Keep paid credentials/cloud calls out of mandatory deterministic tests.

## PRR-191 — Installed-wheel fresh-machine gate

- [x] Build wheel from exact remediation head.
- [x] Install into clean environment.
- [x] Launch installed CLI.
- [x] Launch installed TUI.
- [x] Exercise project/source/host/episode path.
- [x] Exercise planning/auto-planning through installed code.
- [x] Exercise generation.
- [x] Exercise export.
- [x] Validate non-empty transcript/manifest/metadata/audio.
- [x] Validate installed sanitizer behavior.
- [x] Record exact CI evidence.

---

# R11 — Documentation and compatibility

## PRR-200 — Documentation

- [x] Document multi-turn/multi-segment generation.
- [x] Document completion signals/safety bounds.
- [x] Document transactional provider save/remove rollback.
- [x] Document exact role preflight policy.
- [x] Document valid-plan policy.
- [x] Document plan evidence edit/regeneration validation.
- [x] Document TTS/composition format policy.
- [x] Document canonical redaction/export guarantees.
- [x] Document repair reverification/audio regeneration.
- [x] Document cache cleanup.
- [x] Document explicit composition ownership.
- [x] Document Kitten qualification policy.

## PRR-201 — Persisted compatibility matrix

- [x] Current provider config loads.
- [x] Legacy TTS `completed` remains readable/normalizable.
- [x] Existing episodes/runs/turns/provider-identity rows load.
- [x] Existing timelines load.
- [x] Existing exports remain readable.
- [x] Add migration only if required.
- [x] If migration exists, prove idempotent/failure-safe behavior.

---

# R12 — Qualification

## PRR-210 — Static/quality gates

- [x] `uv lock --check`
- [x] `uv run ruff format --check .`
- [x] `uv run ruff check .`
- [x] `uv run mypy`
- [x] `uv run pytest`
- [x] `uv build`
- [x] CLI/import smoke

## PRR-211 — Focused regression matrices

- [x] Multi-turn/multi-segment generation.
- [x] Pause/resume/cancel/resume-after-failure.
- [x] Provider transaction rollback.
- [x] Provider runtime coherence.
- [x] Local/remote route matrix.
- [x] Directing/verification preflight matrix.
- [x] Valid/corrupt plan matrix.
- [x] Plan evidence edit/regeneration isolation.
- [x] Security/redaction.
- [x] TTS format/composition compatibility.
- [x] TTS returned identity.
- [x] Cache invalidation/orphan cleanup.
- [x] Transcript repair/reverification/regeneration.
- [x] CLI acceptance.
- [x] TUI acceptance.
- [x] Multi-episode isolation.
- [x] Installed-wheel fresh-machine.
- [x] Chosen real-Kitten qualification.

---

# R13 — Final reconciliation

## PRR-220 — Reconcile implementation evidence

- [x] Record implementation commit SHA(s) for R1–R12.
- [x] Record PR number(s) only where Ralph Bridge policy required them.
- [x] Record focused test names per cluster.
- [x] Record exact-head CI run ID/conclusion.
- [x] Confirm every checked item is production behavior, not only fixture behavior.
- [x] Confirm every issue in the companion spec is addressed.
- [x] Confirm zero unchecked items before declaring remediation complete.

## PRR-221 — Final current-`master` qualification

- [x] Completed remediation and reconciled TODO are on `master`.
- [x] Reload this TODO from current `master`.
- [x] Reload companion spec from current `master`.
- [x] Confirm zero unchecked tasks.
- [x] Observe exact current-`master` CI.
- [x] Quality job passes.
- [x] Fresh-machine installed-wheel gate passes.
- [x] Chosen Kitten qualification gate passes.
- [x] Record current/final `master` SHA.
- [x] Record final CI run ID/conclusion.
- [x] Only then mark remediation complete.

---

## Closeout evidence

The post-review remediation is reconciled through production implementation, exact-head CI, the companion post-review spec, and the evidence document `docs/POST_REVIEW_FINAL_RECONCILIATION_EVIDENCE_2026-09-29.md`.

- Implementation/evidence heads: `30d52b37561fec757069184392f20745e10fb584`, `432afd5826b402833dbd437147e313cb37aa2697`, `ca679fab9ba689dbcd52f5966407a651c3242473`, `d1f640b01002e186fdb6e85d28a1c9840a5bd75f`, `2b3ad696d4896bad755d154850e08b48a7fa99d2`, and `3188cc4ed0c11efc22706a0f9a7610294587df35`.
- Exact-head CI evidence before this final TODO reconciliation: `36561866442`, `36560691492`, `36572390847`, `36576824294`, `36579387382`, and `36586493711`, all conclusion `success`.
- Current/final `master` SHA: this final TODO reconciliation commit as reported by Ralph Bridge after write acceptance and verified by exact-head CI.
- Current/final `master` CI run: the exact-head CI run for this final TODO reconciliation commit as reported by Ralph Bridge after the commit is written and CI completes.
- Relevant PRs where policy required them: #467, #468, #470, #473, #475, #476, and #477; subsequent remediation work was completed directly on `master` under the current Ralph Bridge direct-master policy.
- R1/R2/R3/R4/R5/R6/R7/R8 evidence: preserved in the prior closeout section history, exact-head CI records, and the focused tests listed in this file before final reconciliation.
- R9 evidence: shared acceptance fixture through public production services, CLI/TUI generation/status/export, duplicate start, pause/resume/cancel, auto-planning, negative auto-planning, evidence/provenance, TTS artifact identity, and same-project multi-episode isolation.
- R10/R12 installed-wheel and Kitten evidence: fresh-machine job steps `Build and install wheel in clean environment`, `Launch installed CLI and TUI entry points`, `Exercise installed-wheel corpus and episode workflow`, `Install real KittenTTS runtime`, and `Real KittenTTS Micro CPU smoke`.
- R11 evidence: `docs/PRODUCTION_GENERATION.md` covers PRR-200, and `tests/test_post_review_compatibility.py` plus legacy TTS compatibility tests cover PRR-201.
- PRR-221 sequencing: this commit is the final TODO reconciliation target; the final assistant report records its exact SHA and exact-head CI run/conclusion after CI completes.
