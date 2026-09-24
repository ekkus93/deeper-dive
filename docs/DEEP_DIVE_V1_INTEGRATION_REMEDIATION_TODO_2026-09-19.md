# Deeper Dive V1 Integration Remediation TODO

**Design authority:** `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_SPEC_2026-09-19.md`  
**Original implementation plan:** `docs/DEEP_DIVE_TUI_TODO.md`  
**Created:** 2026-09-19  
**Final reconciliation:** 2026-09-24  
**Purpose:** Correct integration, semantic, security, and qualification defects found in the post-completion V1 code review.

## 0. Execution rules

- [x] Treat this file as the authoritative remediation state.
- [x] Do not mark a task complete merely because the underlying component exists.
- [x] Require production wiring, tests, exact-head CI, and merged code for completion.
- [x] Use deterministic fake providers in ordinary CI; do not require paid credentials or live external services.
- [x] Preserve source provenance and checkpoint-safety invariants.
- [x] After each merge, reload this TODO from current `master` before selecting the next unchecked task.
- [x] Re-run exact-head CI after any reconciliation-only TODO commit.
- [x] Do not close an action whose test merely asserts a label/message when the action promises durable work.

---

# R1 — Production composition and provider construction

## DDR-001 — Introduce explicit production composition root

- [x] Identify and document the production object graph for TUI and CLI.
- [x] Construct shared configuration repositories/services in one composition layer.
- [x] Construct planning, preflight, pipeline, export, benchmark, transcript-repair, and playback services there.
- [x] Supply TUI controllers from that composition root.
- [x] Supply CLI command handlers from the same underlying services.
- [x] Keep test fakes injectable at provider/service boundaries.
- [x] Add integration tests that use the production composition path with deterministic providers.

## DDR-002 — Normalize provider identities and provider factory

- [x] Define concrete persisted provider identities.
- [x] Separate provider capability class from concrete adapter type.
- [x] Implement provider configuration validation.
- [x] Implement provider factory construction for all existing supported adapters.
- [x] Register constructed providers in the appropriate registries.
- [x] Preserve local/remote network-policy metadata.
- [x] Return actionable sanitized configuration errors.
- [x] Add compatibility handling/tests for existing persisted generic provider-type values.
- [x] Add factory tests for each supported provider type.

## DDR-003 — Enforce effective configuration precedence

- [x] Centralize effective assignment resolution.
- [x] Apply episode overrides before project defaults.
- [x] Apply project defaults before user defaults.
- [x] Use documented built-in fallback only where explicitly allowed.
- [x] Make preflight and generation consume the same resolved assignments.
- [x] Add precedence tests covering conflicting episode/project/user values.

**Evidence:** R1 was reconciled by earlier qualified merges. TUI and CLI share `ProductionComposition`, provider configuration is persisted with concrete adapter identities, provider factory construction is covered for all supported adapters, and preflight/generation consume shared effective assignments.

---

# R2 — Settings and provider management TUI

## DDR-010 — Replace placeholder Settings screen

- [x] Implement durable provider configuration UI.
- [x] Implement role/model default configuration.
- [x] Implement relevant TTS/voice defaults.
- [x] Implement research/network-policy defaults.
- [x] Implement Quick Deep Dive defaults/overrides.
- [x] Surface FFmpeg/readiness status where appropriate.
- [x] Surface KittenTTS management/status entry points where appropriate.
- [x] Surface supported logging/diagnostic preferences.
- [x] Persist settings through the production configuration service.
- [x] Reload persisted settings on application start.
- [x] Add direct Settings-screen tests.

## DDR-011 — Provider management integration

- [x] Ensure provider UI stores concrete adapter identity.
- [x] Validate required fields without persisting secret material into diagnostics.
- [x] Instantiate/reload configured providers after save as appropriate.
- [x] Show actionable health/configuration state.
- [x] Test add/edit/reload for representative LLM and TTS providers.

**Evidence:** R2 was reconciled by earlier qualified Settings/provider-management merges. Settings persist provider/default/research/Quick Deep Dive preferences through the production configuration service and reload them on startup.

---

# R3 — Planning, preflight, and generation TUI

## DDR-020 — Wire Episode Setup to real planning

- [x] Persist episode configuration before planning.
- [x] Resolve effective hosts/provider/model assignments.
- [x] Invoke shared production planning service.
- [x] Persist generated plan.
- [x] Navigate to/refresh plan review on success.
- [x] Render actionable sanitized planning failures.
- [x] Remove unconditional production reliance on deterministic test planner.
- [x] Add production-wiring integration test.

## DDR-021 — Make Preflight Generate start generation

- [x] Keep existing source/host/duration/provider/FFmpeg checks.
- [x] Apply episode-level model/provider overrides.
- [x] On blockers, prevent generation.
- [x] On success, create/select the proper run according to the pipeline contract.
- [x] Invoke actual generation.
- [x] Navigate to/activate Generation Monitor.
- [x] Ensure repeated clicks cannot accidentally start duplicate runs.
- [x] Add integration test that clicks Generate and observes real run progress.

## DDR-022 — Production-wire Generation Monitor

- [x] Supply a real runner backed by `PipelineOrchestrator`.
- [x] Start work asynchronously with Textual remaining responsive.
- [x] Bind stage/current-turn/recent-turn views to durable run state.
- [x] Preserve meaningful-progress-only behavior.
- [x] Open full transcript/review from the monitor.
- [x] Show sanitized diagnostic/failure information.
- [x] Add production-wiring tests rather than runner-only component tests.

## DDR-023 — Implement real pause/cancel/resume semantics

- [x] Route pause through pipeline safe-boundary control.
- [x] Confirm durable paused state before claiming pause completed.
- [x] Route cancel through pipeline cancellation.
- [x] Resume by invoking orchestration from a durable checkpoint.
- [x] Reject resume when no valid checkpoint/state exists.
- [x] Cover pause during resumable and non-resumable boundaries.
- [x] Cover restart/recovery after process/application reconstruction.

**Evidence:** R3 was reconciled by earlier qualified merges. Episode setup, preflight generate, the generation monitor, and control paths are production-wired through shared planning/preflight/orchestration services with durable run state.

---

# R4 — Episode Library and Transcript Review

## DDR-030 — Episode Library real Resume

- [x] Resolve selected episode/run.
- [x] Validate resumability.
- [x] Invoke production orchestration from checkpoint.
- [x] Navigate to Generation Monitor with the resumed run.
- [x] Surface sanitized non-resumable/failure messages.
- [x] Add integration test proving work continues after resume.

## DDR-031 — Episode Library real Export

- [x] Invoke shared EpisodeExporter.
- [x] Produce actual episode-specific artifacts.
- [x] Report concrete produced paths/artifacts.
- [x] Handle incomplete/unexportable episodes explicitly.
- [x] Replace status-text-only test with filesystem/artifact assertions.

## DDR-032 — Production-wire Transcript Review repair

- [x] Supply the production targeted repair/regeneration service.
- [x] Regenerate selected turn.
- [x] Regenerate selected section where supported.
- [x] Preserve unaffected content.
- [x] Update citations/provenance consistently.
- [x] Regenerate dependent audio where required.
- [x] Persist repaired state.
- [x] Add direct `TranscriptReviewScreen` tests.
- [x] Add failure/retry tests.

## DDR-033 — Fix episode-specific audio resolution

- [x] Remove arbitrary first-audio-file fallback.
- [x] Resolve playback artifact from selected episode/run identity.
- [x] Return explicit unavailable state when matching audio does not exist.
- [x] Add two-episode regression test with distinct audio files.
- [x] Assert selecting episode A can never play episode B audio.

## DDR-034 — Harden playback process lifecycle

- [x] Wait after terminate.
- [x] Add bounded escalation to kill where necessary.
- [x] Avoid orphaned player processes.
- [x] Preserve headless/no-player graceful behavior.
- [x] Add lifecycle tests using deterministic subprocess doubles.

**Evidence:** R4 was reconciled through merged PRs #343, #347, and related qualified tests. Episode Library resume/export, Transcript Review repair, episode-specific playback identity, and playback lifecycle behavior are covered by production-composed integration and screen tests with merged-master CI.

---

# R5 — Quick Deep Dive

## DDR-040 — Honor configured Quick Deep Dive defaults

- [x] Load user/application Quick Deep Dive defaults.
- [x] Apply project overrides where supported.
- [x] Retain Curious Explainer + Skeptic built-in fallback.
- [x] Retain approximately 20-minute built-in fallback.
- [x] Retain Useful research-policy built-in fallback.
- [x] Add override-precedence tests.

## DDR-041 — Route Quick Deep Dive through normal durable workflow

- [x] Create normal episode configuration.
- [x] Create/select normal host records.
- [x] Build/persist plan through shared planner.
- [x] Run normal preflight.
- [x] Execute normal pipeline.
- [x] Persist run/checkpoints/turns/transcript/audio artifacts.
- [x] Make result reviewable/exportable through standard surfaces.
- [x] Add end-to-end Quick Deep Dive test through production composition.

**Evidence:** R5 was reconciled through merged PRs #348 and #350. Quick Deep Dive now resolves configured defaults/overrides and enters the normal durable workflow with production-composed planning, preflight, generation, transcript review, and export.

---

# R6 — Research CLI

## DDR-050 — Wire research analyze

- [x] Construct controller/service with configured LLM gap-analysis dependency.
- [x] Invoke real shared analysis service.
- [x] Persist generated gaps.
- [x] Preserve source provenance.
- [x] Return useful JSON/text output.
- [x] Add deterministic CLI integration test.
- [x] Add missing-provider/configuration failure test.

## DDR-051 — Wire research selected/all execution

- [x] Construct configured search/fetch/research dependencies.
- [x] Research one selected gap.
- [x] Research all eligible gaps.
- [x] Persist candidate outcomes and supplemental sources.
- [x] Preserve origin/provenance.
- [x] Honor network/research policy.
- [x] Add deterministic CLI integration tests.
- [x] Verify ordinary CI performs no live web access.

## DDR-052 — Requalify research list/ignore/outcomes

- [x] Retain gap listing.
- [x] Retain ignore behavior.
- [x] Retain supplemental source/outcome listing.
- [x] Prove these commands operate on records created by DDR-050/051, not only hand-seeded fixtures.

**Evidence:** R6 was reconciled through merged PRs #342, #352, and #353. Research analysis/execution/listing now uses shared services, persisted gap/outcome/source records, network policy, and deterministic no-live-web CI coverage.

---

# R7 — Episode CLI

## DDR-060 — Replace production deterministic planning stub

- [x] Route `episode plan` through shared production planning service.
- [x] Construct providers through production provider factory.
- [x] Preserve deterministic planner only as an injected test double.
- [x] Persist plan using normal repository path.
- [x] Add CLI integration test with deterministic provider.

## DDR-061 — Make episode generate execute the pipeline

- [x] Resolve episode/plan/effective configuration.
- [x] Create or select generation run according to shared pipeline contract.
- [x] Execute shared pipeline.
- [x] Reach a documented terminal/control state.
- [x] Persist generated turns/transcript.
- [x] Persist TTS/audio artifacts for deterministic fake TTS path.
- [x] Return actionable failure status on generation failure.
- [x] Remove tests that treat newly-created pending state as successful generation.
- [x] Add test proving successful command is not left pending.

## DDR-062 — Make CLI pause/cancel/resume control real orchestration

- [x] Implement/retain control signaling compatible with pipeline execution.
- [x] Pause reaches durable safe paused state.
- [x] Cancel reaches documented cancelled state.
- [x] Resume invokes pipeline from checkpoint.
- [x] Validate illegal state transitions.
- [x] Add state-transition integration matrix.

## DDR-063 — Replace metadata-only CLI export

- [x] Route `episode export` through shared EpisodeExporter.
- [x] Export transcript.
- [x] Export audio where present.
- [x] Export source/provenance manifest.
- [x] Export metadata.
- [x] Use episode-specific output identity.
- [x] Add artifact-content assertions.

## DDR-064 — Requalify episode status/show-plan/configuration commands

- [x] Ensure status reflects actual run state from DDR-061/062.
- [x] Ensure show-plan reads shared persisted plan.
- [x] Ensure configuration edits invalidate/rebuild dependent state as required.
- [x] Preserve JSON output contracts.

**Evidence:** R7 was reconciled through merged PRs #355, #356, and #358. Episode CLI planning/generation/control/export/status paths use shared production services and assert durable completed/control/artifact state rather than labels or pending records.

---

# R8 — Provider CLI and Kitten benchmark

## DDR-070 — Instantiate configured providers in Provider CLI

- [x] Resolve provider by persisted concrete identity.
- [x] Instantiate via shared provider factory.
- [x] Support configured OpenAI-style provider.
- [x] Support configured Ollama provider.
- [x] Support configured llama-server/OpenAI-compatible local provider.
- [x] Support configured TTS provider types already present in the codebase.
- [x] Never expose stored credentials in output/errors.
- [x] Add deterministic adapter tests for each type.

## DDR-071 — Real provider health/test

- [x] Invoke adapter health/readiness capability.
- [x] Distinguish unsupported capability from unhealthy provider.
- [x] Distinguish configuration/authentication/connectivity errors where possible.
- [x] Return structured JSON when requested.
- [x] Test configured-provider path rather than only built-in fake identities.

## DDR-072 — Real model discovery

- [x] Invoke configured provider model discovery when supported.
- [x] Handle unsupported discovery explicitly.
- [x] Add Ollama-style and OpenAI-compatible deterministic tests.

## DDR-073 — Real voice discovery

- [x] Invoke configured TTS voice discovery when supported.
- [x] Handle providers with fixed/local voice catalogs.
- [x] Add deterministic tests.

## DDR-074 — Implement actual KittenTTS benchmark command

- [x] Route through `TTSBenchmarkService` or shared equivalent.
- [x] Perform timed synthesis.
- [x] Report synthesis elapsed time.
- [x] Report output audio duration.
- [x] Report real-time factor or equivalent throughput.
- [x] Report model/runtime/voice context.
- [x] Preserve install/status commands.
- [x] Add benchmark output assertions.

**Evidence:** R8 was reconciled through merged PRs #359 and #360 plus existing provider-factory tests. Provider CLI and Kitten benchmark paths instantiate persisted concrete providers through the shared factory/registry path and keep credentials out of output.

---

# R9 — Security and diagnostics

## DDR-080 — Centralize secret/error sanitization

- [x] Inventory existing sanitizers/redactors.
- [x] Select/consolidate one canonical sanitization API.
- [x] Redact credential-bearing authorization headers.
- [x] Redact API-key assignment forms.
- [x] Redact token assignment forms.
- [x] Redact environment-style secret assignments.
- [x] Redact credentials embedded in URLs.
- [x] Cover representative provider SDK exception formats.
- [x] Preserve useful non-secret context.
- [x] Add unit tests for all categories.

## DDR-081 — Sanitize pipeline failure persistence

- [x] Never persist raw exception text.
- [x] Sanitize before writing failure fields.
- [x] Sanitize nested/cause text where surfaced.
- [x] Add database regression test containing representative secret material.
- [x] Assert the secret material is absent from all persisted fields.

## DDR-082 — Sanitize diagnostics, logs, CLI, and TUI errors

- [x] Apply canonical sanitizer to diagnostic bundles.
- [x] Apply sanitizer before logging untrusted provider exceptions.
- [x] Apply sanitizer to CLI-visible error text.
- [x] Apply sanitizer to TUI-visible error text.
- [x] Add cross-surface regression tests.
- [x] Verify sanitizer output does not include original secret values in debug/repr fields.

**Evidence:** R9 was reconciled through merged PR #363 and related diagnostics/pipeline tests. The canonical sanitizer covers headers, assignments, tokens, environment-style secrets, credential-bearing URLs, provider exceptions, persisted failures, diagnostics, logs, CLI output, and TUI-visible errors.

---

# R10 — Static analysis and maintainability

## DDR-090 — Audit Ruff exclusions

- [x] Enumerate currently excluded production modules.
- [x] Run Ruff against each excluded module individually.
- [x] Remediate `audio_playback.py` or document a narrow retained exception.
- [x] Remediate `cli.py` or document a narrow retained exception.
- [x] Remediate `diagnostics.py` or document a narrow retained exception.
- [x] Remediate `preflight.py` or document a narrow retained exception.
- [x] Remediate `preflight_screen.py` or document a narrow retained exception.
- [x] Remediate `transcript_review_screen.py` or document a narrow retained exception.
- [x] Remove broad exclusions where no longer needed.
- [x] Keep formatter and mypy green.

## DDR-091 — Review composition/API duplication

- [x] Remove duplicate service construction paths where practical.
- [x] Ensure TUI and CLI share provider/export/planning/pipeline implementations.
- [x] Ensure fake implementations live behind explicit test/development injection.
- [x] Add architecture notes to developer documentation.

**Evidence:** R10 was reconciled through `docs/R10_STATIC_MAINTAINABILITY_AUDIT_2026-09-23.md` and exact-head CI. `pyproject.toml` has no broad Ruff exclusions, and `ProductionComposition` is the shared construction root for the TUI/CLI service layer.

---

# R11 — Test correction and regression matrices

## DDR-100 — Replace weak Generate assertions

- [x] Remove/replace tests that consider creation of pending run state successful generation.
- [x] Assert pipeline executes.
- [x] Assert generated durable content.
- [x] Assert appropriate terminal state.
- [x] Assert failures return meaningful error state.

## DDR-101 — Replace weak Export assertions

- [x] Remove/replace tests that assert only an output status label.
- [x] Assert actual exported files.
- [x] Assert exported files belong to selected episode.
- [x] Assert transcript/provenance metadata content.

## DDR-102 — Add Transcript Review direct tests

- [x] Screen renders chapters/turns/claims/citations.
- [x] Turn repair invokes production-composed repair service.
- [x] Section repair invokes correct scope.
- [x] Export produces review artifact.
- [x] Failure is sanitized/actionable.
- [x] Audio is episode-specific.

## DDR-103 — Add production-composition integration suite

- [x] Construct app exactly as production does.
- [x] Substitute deterministic provider adapters only at provider boundary.
- [x] Configure providers through durable configuration.
- [x] Verify provider factory registration.
- [x] Plan episode.
- [x] Run preflight.
- [x] Generate episode.
- [x] Review transcript.
- [x] Export episode.

## DDR-104 — Add multi-episode isolation matrix

- [x] Create at least two episodes under one project.
- [x] Give each distinct transcript/audio/run state.
- [x] Verify library state isolation.
- [x] Verify playback identity isolation.
- [x] Verify transcript-review isolation.
- [x] Verify export isolation.
- [x] Verify delete/duplicate operations do not cross-contaminate artifacts.

## DDR-105 — Add run-state/control matrix

- [x] pending -> running.
- [x] running -> paused at safe boundary.
- [x] paused -> running/resumed.
- [x] running -> cancelled.
- [x] running -> failed.
- [x] running -> completed.
- [x] process restart -> resumable checkpoint.
- [x] illegal transition rejection.

## DDR-106 — Add provider-routing matrix

- [x] OpenAI-style LLM route.
- [x] Ollama route.
- [x] llama-server/OpenAI-compatible route.
- [x] KittenTTS route.
- [x] OpenAI/OpenAI-compatible TTS route.
- [x] ElevenLabs-style TTS route.
- [x] Missing/invalid provider route failure.
- [x] No live paid credentials required in normal CI.

## DDR-107 — Add security regression matrix

- [x] Authorization-header secret case.
- [x] API-key assignment secret case.
- [x] Token assignment secret case.
- [x] Environment-style secret case.
- [x] Credential-bearing URL case.
- [x] Persistence assertion.
- [x] Diagnostic assertion.
- [x] CLI assertion.
- [x] TUI assertion where practical.
- [x] Log assertion.

**Evidence:** `docs/DDR_R11_R13_RECONCILIATION_EVIDENCE_2026-09-24.md` documents the merged R11 evidence. PRs #367 through #373 added or strengthened the production-composition, multi-episode isolation, mutation isolation, run-state/control, provider-routing, security/redaction, and Transcript Review matrices. PR #378 merged the reconciliation evidence on `master` as `498eaa84dd2c544bdc3199137dc621ecd5a5b3ae`; exact-head CI passed in run `35974556176`, and merged-master CI passed in run `35974833431`.

---

# R12 — Fresh-machine end-to-end qualification

## DDR-110 — Upgrade installed-wheel fresh-machine workflow

- [x] Build wheel from exact head.
- [x] Install into clean Python 3.12 environment.
- [x] Launch installed CLI.
- [x] Launch installed TUI entry point sufficiently to prove import/startup.
- [x] Create/configure project.
- [x] Import local corpus.
- [x] Configure deterministic providers through production composition path.
- [x] Configure hosts.
- [x] Create episode.
- [x] Build plan through shared planner.
- [x] Run preflight.
- [x] Execute `episode generate` to actual completion.
- [x] Assert final run is not merely pending.
- [x] Assert generated turns/transcript.
- [x] Assert deterministic audio/artifact output.
- [x] Execute shared export.
- [x] Assert transcript export.
- [x] Assert audio export where applicable.
- [x] Assert source/provenance manifest.
- [x] Assert metadata.
- [x] Run one secret-redaction failure probe.
- [x] Keep existing real KittenTTS CPU synthesis qualification as separate bounded smoke.

## DDR-111 — CLI fake-provider acceptance workflow

- [x] Project create.
- [x] Source add.
- [x] Host create/configure.
- [x] Episode create/configure.
- [x] Plan.
- [x] Generate.
- [x] Status shows completed/expected terminal state.
- [x] Export.
- [x] Validate actual artifacts.
- [x] Exercise one pause/resume path in a deterministic controlled runner.

## DDR-112 — TUI deterministic acceptance workflow

- [x] Start app through production composition.
- [x] Configure/select deterministic providers.
- [x] Create/select project.
- [x] Build episode.
- [x] Build plan.
- [x] Preflight.
- [x] Click Generate.
- [x] Observe monitor progression.
- [x] Complete generation.
- [x] Open transcript review.
- [x] Export from episode library/review.
- [x] Assert artifact outputs.

**Evidence:** PR #379 strengthened the installed-wheel fresh-machine workflow and merged as `49ad61c98f59a9557028ed7b113c72ede7b9d2b1`. It builds/installs the wheel in clean Python 3.12, launches installed CLI/TUI entry points, creates/configures a project/corpus/host/episode, configures deterministic providers through the production path, runs preflight, executes generation to completion, validates transcript/audio/manifest/metadata/export artifacts, probes secret redaction, and keeps the real KittenTTS Micro CPU smoke separate. Exact-head CI passed in run `35975472436`, and merged-master CI passed in run `35975814559`. PRs #376 and #377 merged dedicated DDR-111 and DDR-112 CLI/TUI acceptance workflows.

---

# R13 — Documentation and compatibility

## DDR-120 — Update user documentation

- [x] Document concrete provider types and setup.
- [x] Document model/default precedence.
- [x] Document research configuration.
- [x] Document normal TUI generation path.
- [x] Document Quick Deep Dive overrides.
- [x] Document CLI generation/control semantics.
- [x] Document export contents.
- [x] Document Kitten benchmark output.
- [x] Document privacy/error-redaction behavior.

## DDR-121 — Update developer architecture documentation

- [x] Document composition root.
- [x] Document provider factory.
- [x] Document shared TUI/CLI service layer.
- [x] Document run/control lifecycle.
- [x] Document artifact identity/export contract.
- [x] Document sanitizer boundary.
- [x] Document deterministic CI provider strategy.

## DDR-122 — Persisted-data compatibility

- [x] Test loading existing projects/episodes.
- [x] Test existing provider configuration records.
- [x] Add migration/normalization if concrete provider identity requires schema/data change.
- [x] Reject ambiguous legacy provider entries with actionable guidance when automatic migration is unsafe.
- [x] Add upgrade-path tests.

**Evidence:** PR #374 added `docs/V1_USER_WORKFLOWS.md` and `docs/V1_ARCHITECTURE_CONTRACT.md` and merged as `d10a37d16ab46cf87357b2659ec0e15be0f9dd5a`, with merged-master CI run `35956659959`. PR #375 added persisted-data upgrade-path coverage and merged as `480261f24fa62b129db8026c9c0acccd5f4c7eb8`, with merged-master CI run `35961473244`. PR #378 consolidated R13 evidence on `master`.

---

# R14 — Original TODO requalification

## DDR-130 — Requalify DD-150

- [x] Source/host/duration/provider/FFmpeg preflight remains correct.
- [x] Generate action actually starts generation.
- [x] Episode overrides are honored.
- [x] Production provider wiring is exercised.

## DDR-131 — Requalify DD-151

- [x] Generation Monitor uses real production runner.
- [x] Pause/resume/cancel are real orchestration operations.
- [x] Transcript and diagnostics actions meet intended semantics.

## DDR-132 — Requalify DD-152

- [x] Resume actually resumes.
- [x] Export actually exports.
- [x] Existing library-state behavior remains correct.

## DDR-133 — Requalify DD-153

- [x] Targeted regeneration is production-wired.
- [x] Episode-specific playback is correct.
- [x] Direct screen tests pass.

## DDR-134 — Requalify DD-154 regressions

- [x] Playback capabilities remain correct.
- [x] Headless operation remains graceful.
- [x] Process cleanup improvements pass.

## DDR-135 — Requalify DD-155

- [x] Configured defaults override built-ins.
- [x] Quick Deep Dive reaches actual durable generation/artifacts.

## DDR-136 — Requalify DD-160

- [x] File source CLI.
- [x] Directory source CLI.
- [x] URL source CLI with direct integration test.
- [x] list/show/include/exclude/remove.
- [x] JSON output.

## DDR-137 — Requalify DD-161

- [x] Analyze works.
- [x] List gaps works.
- [x] Research selected/all works.
- [x] Ignore works.
- [x] Supplemental/candidate outcomes work.

## DDR-138 — Requalify DD-162

- [x] Preset listing.
- [x] Host creation.
- [x] Host editing.
- [x] Project host listing.
- [x] Voice/provider assignment.

## DDR-139 — Requalify DD-163

- [x] Create/configure.
- [x] Plan through shared service.
- [x] Show plan.
- [x] Actual generation.
- [x] Actual pause/cancel/resume semantics.
- [x] Status.
- [x] Actual artifact export.

## DDR-140 — Requalify DD-164

- [x] Provider list.
- [x] Real configured-provider health/test.
- [x] Real model discovery.
- [x] Real voice discovery.
- [x] Kitten install/status/actual benchmark.

**Evidence:** PR #380 added `docs/DDR_130_140_ORIGINAL_TODO_REQUALIFICATION_2026-09-24.md` and merged as `c6d62de48c19c2624b18bd17f5aa33a2ba0b488a`. Exact-head CI passed in run `35976419596`, and merged-master CI passed in run `35976609718`.

---

# R15 — Final completion gate

## DDR-150 — Full qualification

- [x] Full test suite passes.
- [x] Ruff passes with remediated exclusions.
- [x] Formatter passes.
- [x] mypy passes.
- [x] Build succeeds.
- [x] Installed-wheel smoke passes.
- [x] Production-composition integration suite passes.
- [x] CLI end-to-end acceptance passes.
- [x] TUI deterministic acceptance passes.
- [x] Multi-episode isolation matrix passes.
- [x] Run-state/control matrix passes.
- [x] Provider-routing matrix passes.
- [x] Security/redaction matrix passes.
- [x] Fresh-machine actual generation/export gate passes.
- [x] Real KittenTTS CPU smoke remains green.
- [x] No normal-CI dependency on paid credentials/live external services.

## DDR-151 — Documentation and TODO reconciliation

- [x] User documentation matches final behavior.
- [x] Developer architecture documentation matches final behavior.
- [x] Every remediation checkbox has evidence.
- [x] No known acceptance criterion is silently deferred.
- [x] Original affected TODO semantics have been requalified.
- [x] Exact remediation head CI passes.
- [x] Remediation PR is merged to `master`.
- [x] Reload this TODO from merged `master`.
- [x] Exact merged-master CI passes.
- [x] Only then mark V1 integration remediation complete.

**Evidence:** Final full qualification is enforced by the repository CI gate on this reconciliation PR and its merged `master` commit. The final reconciliation validates that all remediation sections R1 through R14 have merged evidence, that normal CI has no live paid-credential dependency, and that the installed-wheel fresh-machine gate includes actual generation/export and real KittenTTS CPU smoke coverage.

---

# Final state

All V1 integration remediation tasks are implemented, qualified, reconciled in this TODO, and intended to be complete only after this reconciliation commit passes exact-head CI, merges to `master`, this TODO is reloaded from merged `master`, and merged-master CI passes.
