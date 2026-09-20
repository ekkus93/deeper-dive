# Deeper Dive V1 Integration Remediation TODO

**Design authority:** `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_SPEC_2026-09-19.md`  
**Original implementation plan:** `docs/DEEP_DIVE_TUI_TODO.md`  
**Created:** 2026-09-19  
**Purpose:** Correct integration, semantic, security, and qualification defects found in the post-completion V1 code review.

## 0. Execution rules

- [ ] Treat this file as the authoritative remediation state.
- [ ] Do not mark a task complete merely because the underlying component exists.
- [ ] Require production wiring, tests, exact-head CI, and merged code for completion.
- [ ] Use deterministic fake providers in ordinary CI; do not require paid credentials or live external services.
- [ ] Preserve source provenance and checkpoint-safety invariants.
- [ ] After each merge, reload this TODO from current `master` before selecting the next unchecked task.
- [ ] Re-run exact-head CI after any reconciliation-only TODO commit.
- [ ] Do not close an action whose test merely asserts a label/message when the action promises durable work.

---

# R1 — Production composition and provider construction

## DDR-001 — Introduce explicit production composition root

- [x] Identify and document the production object graph for TUI and CLI.
- [x] Construct shared configuration repositories/services in one composition layer.
- [ ] Construct planning, preflight, pipeline, export, benchmark, transcript-repair, and playback services there.
- [ ] Supply TUI controllers from that composition root.
- [ ] Supply CLI command handlers from the same underlying services.
- [ ] Keep test fakes injectable at provider/service boundaries.
- [ ] Add integration tests that use the production composition path with deterministic providers.

**Acceptance criteria**

- TUI and CLI tests no longer need to manually inject capabilities that production construction omits.
- A production-composed deterministic application can plan and generate an episode.

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

**Acceptance criteria**

- A provider saved through normal configuration can subsequently be instantiated without test-only registry injection.

## DDR-003 — Enforce effective configuration precedence

- [x] Centralize effective assignment resolution.
- [ ] Apply episode overrides before project defaults.
- [ ] Apply project defaults before user defaults.
- [ ] Use documented built-in fallback only where explicitly allowed.
- [ ] Make preflight and generation consume the same resolved assignments.
- [x] Add precedence tests covering conflicting episode/project/user values.

**Acceptance criteria**

- Preflight reports the exact provider/model assignments generation will use.

---

# R2 — Settings and provider management TUI

## DDR-010 — Replace placeholder Settings screen

- [ ] Implement durable provider configuration UI.
- [ ] Implement role/model default configuration.
- [ ] Implement relevant TTS/voice defaults.
- [ ] Implement research/network-policy defaults.
- [ ] Implement Quick Deep Dive defaults/overrides.
- [ ] Surface FFmpeg/readiness status where appropriate.
- [ ] Surface KittenTTS management/status entry points where appropriate.
- [ ] Surface supported logging/diagnostic preferences.
- [ ] Persist settings through the production configuration service.
- [ ] Reload persisted settings on application start.
- [ ] Add direct Settings-screen tests.

**Acceptance criteria**

- A user can configure the defaults consumed by preflight, planning, Quick Deep Dive, and provider construction without editing files manually.

## DDR-011 — Provider management integration

- [ ] Ensure provider UI stores concrete adapter identity.
- [ ] Validate required fields without persisting secret material into diagnostics.
- [ ] Instantiate/reload configured providers after save as appropriate.
- [ ] Show actionable health/configuration state.
- [ ] Test add/edit/reload for representative LLM and TTS providers.

---

# R3 — Planning, preflight, and generation TUI

## DDR-020 — Wire Episode Setup to real planning

- [x] Persist episode configuration before planning.
- [ ] Resolve effective hosts/provider/model assignments.
- [x] Invoke shared production planning service.
- [x] Persist generated plan.
- [x] Navigate to/refresh plan review on success.
- [x] Render actionable sanitized planning failures.
- [x] Remove unconditional production reliance on deterministic test planner.
- [ ] Add production-wiring integration test.

**Acceptance criteria**

- Clicking Build Plan produces a persisted plan through the same planning service used by CLI.

## DDR-021 — Make Preflight Generate start generation

- [ ] Keep existing source/host/duration/provider/FFmpeg checks.
- [ ] Apply episode-level model/provider overrides.
- [ ] On blockers, prevent generation.
- [ ] On success, create/select the proper run according to the pipeline contract.
- [ ] Invoke actual generation.
- [ ] Navigate to/activate Generation Monitor.
- [ ] Ensure repeated clicks cannot accidentally start duplicate runs.
- [ ] Add integration test that clicks Generate and observes real run progress.

**Acceptance criteria**

- Generate never stops at "ready"; it starts the pipeline.

## DDR-022 — Production-wire Generation Monitor

- [ ] Supply a real runner backed by `PipelineOrchestrator`.
- [ ] Start work asynchronously with Textual remaining responsive.
- [ ] Bind stage/current-turn/recent-turn views to durable run state.
- [ ] Preserve meaningful-progress-only behavior.
- [ ] Open full transcript/review from the monitor.
- [ ] Show sanitized diagnostic/failure information.
- [ ] Add production-wiring tests rather than runner-only component tests.

## DDR-023 — Implement real pause/cancel/resume semantics

- [ ] Route pause through pipeline safe-boundary control.
- [ ] Confirm durable paused state before claiming pause completed.
- [ ] Route cancel through pipeline cancellation.
- [ ] Resume by invoking orchestration from a durable checkpoint.
- [ ] Reject resume when no valid checkpoint/state exists.
- [ ] Cover pause during resumable and non-resumable boundaries.
- [ ] Cover restart/recovery after process/application reconstruction.

**Acceptance criteria**

- State fields are consequences of pipeline control, not substitutes for it.

---

# R4 — Episode Library and Transcript Review

## DDR-030 — Episode Library real Resume

- [ ] Resolve selected episode/run.
- [ ] Validate resumability.
- [ ] Invoke production orchestration from checkpoint.
- [ ] Navigate to Generation Monitor with the resumed run.
- [ ] Surface sanitized non-resumable/failure messages.
- [ ] Add integration test proving work continues after resume.

## DDR-031 — Episode Library real Export

- [ ] Invoke shared EpisodeExporter.
- [ ] Produce actual episode-specific artifacts.
- [ ] Report concrete produced paths/artifacts.
- [ ] Handle incomplete/unexportable episodes explicitly.
- [ ] Replace status-text-only test with filesystem/artifact assertions.

**Acceptance criteria**

- Export creates real output; displaying an output-directory name alone fails the test.

## DDR-032 — Production-wire Transcript Review repair

- [ ] Supply the production targeted repair/regeneration service.
- [ ] Regenerate selected turn.
- [ ] Regenerate selected section where supported.
- [ ] Preserve unaffected content.
- [ ] Update citations/provenance consistently.
- [ ] Regenerate dependent audio where required.
- [ ] Persist repaired state.
- [ ] Add direct `TranscriptReviewScreen` tests.
- [ ] Add failure/retry tests.

## DDR-033 — Fix episode-specific audio resolution

- [ ] Remove arbitrary first-audio-file fallback.
- [ ] Resolve playback artifact from selected episode/run identity.
- [ ] Return explicit unavailable state when matching audio does not exist.
- [ ] Add two-episode regression test with distinct audio files.
- [ ] Assert selecting episode A can never play episode B audio.

## DDR-034 — Harden playback process lifecycle

- [ ] Wait after terminate.
- [ ] Add bounded escalation to kill where necessary.
- [ ] Avoid orphaned player processes.
- [ ] Preserve headless/no-player graceful behavior.
- [ ] Add lifecycle tests using deterministic subprocess doubles.

---

# R5 — Quick Deep Dive

## DDR-040 — Honor configured Quick Deep Dive defaults

- [ ] Load user/application Quick Deep Dive defaults.
- [ ] Apply project overrides where supported.
- [ ] Retain Curious Explainer + Skeptic built-in fallback.
- [ ] Retain approximately 20-minute built-in fallback.
- [ ] Retain Useful research-policy built-in fallback.
- [ ] Add override-precedence tests.

## DDR-041 — Route Quick Deep Dive through normal durable workflow

- [ ] Create normal episode configuration.
- [ ] Create/select normal host records.
- [ ] Build/persist plan through shared planner.
- [ ] Run normal preflight.
- [ ] Execute normal pipeline.
- [ ] Persist run/checkpoints/turns/transcript/audio artifacts.
- [ ] Make result reviewable/exportable through standard surfaces.
- [ ] Add end-to-end Quick Deep Dive test through production composition.

**Acceptance criteria**

- Quick Deep Dive is a convenience entry point, not a separate placeholder implementation.

---

# R6 — Research CLI

## DDR-050 — Wire research analyze

- [ ] Construct controller/service with configured LLM gap-analysis dependency.
- [ ] Invoke real shared analysis service.
- [ ] Persist generated gaps.
- [ ] Preserve source provenance.
- [ ] Return useful JSON/text output.
- [ ] Add deterministic CLI integration test.
- [ ] Add missing-provider/configuration failure test.

## DDR-051 — Wire research selected/all execution

- [ ] Construct configured search/fetch/research dependencies.
- [ ] Research one selected gap.
- [ ] Research all eligible gaps.
- [ ] Persist candidate outcomes and supplemental sources.
- [ ] Preserve origin/provenance.
- [ ] Honor network/research policy.
- [ ] Add deterministic CLI integration tests.
- [ ] Verify ordinary CI performs no live web access.

## DDR-052 — Requalify research list/ignore/outcomes

- [ ] Retain gap listing.
- [ ] Retain ignore behavior.
- [ ] Retain supplemental source/outcome listing.
- [ ] Prove these commands operate on records created by DDR-050/051, not only hand-seeded fixtures.

---

# R7 — Episode CLI

## DDR-060 — Replace production deterministic planning stub

- [ ] Route `episode plan` through shared production planning service.
- [ ] Construct providers through production provider factory.
- [ ] Preserve deterministic planner only as an injected test double.
- [ ] Persist plan using normal repository path.
- [ ] Add CLI integration test with deterministic provider.

## DDR-061 — Make episode generate execute the pipeline

- [ ] Resolve episode/plan/effective configuration.
- [ ] Create or select generation run according to shared pipeline contract.
- [ ] Execute shared pipeline.
- [ ] Reach a documented terminal/control state.
- [ ] Persist generated turns/transcript.
- [ ] Persist TTS/audio artifacts for deterministic fake TTS path.
- [ ] Return actionable failure status on generation failure.
- [ ] Remove tests that treat newly-created pending state as successful generation.
- [ ] Add test proving successful command is not left pending.

**Acceptance criteria**

- `episode generate` produces generated episode state, not merely a run record.

## DDR-062 — Make CLI pause/cancel/resume control real orchestration

- [ ] Implement/retain control signaling compatible with pipeline execution.
- [ ] Pause reaches durable safe paused state.
- [ ] Cancel reaches documented cancelled state.
- [ ] Resume invokes pipeline from checkpoint.
- [ ] Validate illegal state transitions.
- [ ] Add state-transition integration matrix.

## DDR-063 — Replace metadata-only CLI export

- [ ] Route `episode export` through shared EpisodeExporter.
- [ ] Export transcript.
- [ ] Export audio where present.
- [ ] Export source/provenance manifest.
- [ ] Export metadata.
- [ ] Use episode-specific output identity.
- [ ] Add artifact-content assertions.

## DDR-064 — Requalify episode status/show-plan/configuration commands

- [ ] Ensure status reflects actual run state from DDR-061/062.
- [ ] Ensure show-plan reads shared persisted plan.
- [ ] Ensure configuration edits invalidate/rebuild dependent state as required.
- [ ] Preserve JSON output contracts.

---

# R8 — Provider CLI and Kitten benchmark

## DDR-070 — Instantiate configured providers in Provider CLI

- [ ] Resolve provider by persisted concrete identity.
- [ ] Instantiate via shared provider factory.
- [ ] Support configured OpenAI-style provider.
- [ ] Support configured Ollama provider.
- [ ] Support configured llama-server/OpenAI-compatible local provider.
- [ ] Support configured TTS provider types already present in the codebase.
- [ ] Never expose stored credentials in output/errors.
- [ ] Add deterministic adapter tests for each type.

## DDR-071 — Real provider health/test

- [ ] Invoke adapter health/readiness capability.
- [ ] Distinguish unsupported capability from unhealthy provider.
- [ ] Distinguish configuration/authentication/connectivity errors where possible.
- [ ] Return structured JSON when requested.
- [ ] Test configured-provider path rather than only built-in fake identities.

## DDR-072 — Real model discovery

- [ ] Invoke configured provider model discovery when supported.
- [ ] Handle unsupported discovery explicitly.
- [ ] Add Ollama-style and OpenAI-compatible deterministic tests.

## DDR-073 — Real voice discovery

- [ ] Invoke configured TTS voice discovery when supported.
- [ ] Handle providers with fixed/local voice catalogs.
- [ ] Add deterministic tests.

## DDR-074 — Implement actual KittenTTS benchmark command

- [ ] Route through `TTSBenchmarkService` or shared equivalent.
- [ ] Perform timed synthesis.
- [ ] Report synthesis elapsed time.
- [ ] Report output audio duration.
- [ ] Report real-time factor or equivalent throughput.
- [ ] Report model/runtime/voice context.
- [ ] Preserve install/status commands.
- [ ] Add benchmark output assertions.

---

# R9 — Security and diagnostics

## DDR-080 — Centralize secret/error sanitization

- [ ] Inventory existing sanitizers/redactors.
- [ ] Select/consolidate one canonical sanitization API.
- [ ] Redact credential-bearing authorization headers.
- [ ] Redact API-key assignment forms.
- [ ] Redact token assignment forms.
- [ ] Redact environment-style secret assignments.
- [ ] Redact credentials embedded in URLs.
- [ ] Cover representative provider SDK exception formats.
- [ ] Preserve useful non-secret context.
- [ ] Add unit tests for all categories.

## DDR-081 — Sanitize pipeline failure persistence

- [ ] Never persist raw exception text.
- [ ] Sanitize before writing failure fields.
- [ ] Sanitize nested/cause text where surfaced.
- [ ] Add database regression test containing representative secret material.
- [ ] Assert the secret material is absent from all persisted fields.

## DDR-082 — Sanitize diagnostics, logs, CLI, and TUI errors

- [ ] Apply canonical sanitizer to diagnostic bundles.
- [ ] Apply sanitizer before logging untrusted provider exceptions.
- [ ] Apply sanitizer to CLI-visible error text.
- [ ] Apply sanitizer to TUI-visible error text.
- [ ] Add cross-surface regression tests.
- [ ] Verify sanitizer output does not include original secret values in debug/repr fields.

---

# R10 — Static analysis and maintainability

## DDR-090 — Audit Ruff exclusions

- [ ] Enumerate currently excluded production modules.
- [ ] Run Ruff against each excluded module individually.
- [ ] Remediate `audio_playback.py` or document a narrow retained exception.
- [ ] Remediate `cli.py` or document a narrow retained exception.
- [ ] Remediate `diagnostics.py` or document a narrow retained exception.
- [ ] Remediate `preflight.py` or document a narrow retained exception.
- [ ] Remediate `preflight_screen.py` or document a narrow retained exception.
- [ ] Remediate `transcript_review_screen.py` or document a narrow retained exception.
- [ ] Remove broad exclusions where no longer needed.
- [ ] Keep formatter and mypy green.

## DDR-091 — Review composition/API duplication

- [ ] Remove duplicate service construction paths where practical.
- [ ] Ensure TUI and CLI share provider/export/planning/pipeline implementations.
- [ ] Ensure fake implementations live behind explicit test/development injection.
- [ ] Add architecture notes to developer documentation.

---

# R11 — Test correction and regression matrices

## DDR-100 — Replace weak Generate assertions

- [ ] Remove/replace tests that consider creation of pending run state successful generation.
- [ ] Assert pipeline executes.
- [ ] Assert generated durable content.
- [ ] Assert appropriate terminal state.
- [ ] Assert failures return meaningful error state.

## DDR-101 — Replace weak Export assertions

- [ ] Remove/replace tests that assert only an output status label.
- [ ] Assert actual exported files.
- [ ] Assert exported files belong to selected episode.
- [ ] Assert transcript/provenance metadata content.

## DDR-102 — Add Transcript Review direct tests

- [ ] Screen renders chapters/turns/claims/citations.
- [ ] Turn repair invokes production-composed repair service.
- [ ] Section repair invokes correct scope.
- [ ] Export produces review artifact.
- [ ] Failure is sanitized/actionable.
- [ ] Audio is episode-specific.

## DDR-103 — Add production-composition integration suite

- [ ] Construct app exactly as production does.
- [ ] Substitute deterministic provider adapters only at provider boundary.
- [ ] Configure providers through durable configuration.
- [ ] Verify provider factory registration.
- [ ] Plan episode.
- [ ] Run preflight.
- [ ] Generate episode.
- [ ] Review transcript.
- [ ] Export episode.

## DDR-104 — Add multi-episode isolation matrix

- [ ] Create at least two episodes under one project.
- [ ] Give each distinct transcript/audio/run state.
- [ ] Verify library state isolation.
- [ ] Verify playback identity isolation.
- [ ] Verify transcript-review isolation.
- [ ] Verify export isolation.
- [ ] Verify delete/duplicate operations do not cross-contaminate artifacts.

## DDR-105 — Add run-state/control matrix

- [ ] pending -> running.
- [ ] running -> paused at safe boundary.
- [ ] paused -> running/resumed.
- [ ] running -> cancelled.
- [ ] running -> failed.
- [ ] running -> completed.
- [ ] process restart -> resumable checkpoint.
- [ ] illegal transition rejection.

## DDR-106 — Add provider-routing matrix

- [ ] OpenAI-style LLM route.
- [ ] Ollama route.
- [ ] llama-server/OpenAI-compatible route.
- [ ] KittenTTS route.
- [ ] OpenAI/OpenAI-compatible TTS route.
- [ ] ElevenLabs-style TTS route.
- [ ] Missing/invalid provider route failure.
- [ ] No live paid credentials required in normal CI.

## DDR-107 — Add security regression matrix

- [ ] Authorization-header secret case.
- [ ] API-key assignment secret case.
- [ ] Token assignment secret case.
- [ ] Environment-style secret case.
- [ ] Credential-bearing URL case.
- [ ] Persistence assertion.
- [ ] Diagnostic assertion.
- [ ] CLI assertion.
- [ ] TUI assertion where practical.
- [ ] Log assertion.

---

# R12 — Fresh-machine end-to-end qualification

## DDR-110 — Upgrade installed-wheel fresh-machine workflow

- [ ] Build wheel from exact head.
- [ ] Install into clean Python 3.12 environment.
- [ ] Launch installed CLI.
- [ ] Launch installed TUI entry point sufficiently to prove import/startup.
- [ ] Create/configure project.
- [ ] Import local corpus.
- [ ] Configure deterministic providers through production composition path.
- [ ] Configure hosts.
- [ ] Create episode.
- [ ] Build plan through shared planner.
- [ ] Run preflight.
- [ ] Execute `episode generate` to actual completion.
- [ ] Assert final run is not merely pending.
- [ ] Assert generated turns/transcript.
- [ ] Assert deterministic audio/artifact output.
- [ ] Execute shared export.
- [ ] Assert transcript export.
- [ ] Assert audio export where applicable.
- [ ] Assert source/provenance manifest.
- [ ] Assert metadata.
- [ ] Run one secret-redaction failure probe.
- [ ] Keep existing real KittenTTS CPU synthesis qualification as separate bounded smoke.

**Acceptance criteria**

- The clean installed wheel proves actual generation and export semantics without source-tree imports.

## DDR-111 — CLI fake-provider acceptance workflow

- [ ] Project create.
- [ ] Source add.
- [ ] Host create/configure.
- [ ] Episode create/configure.
- [ ] Plan.
- [ ] Generate.
- [ ] Status shows completed/expected terminal state.
- [ ] Export.
- [ ] Validate actual artifacts.
- [ ] Exercise one pause/resume path in a deterministic controlled runner.

## DDR-112 — TUI deterministic acceptance workflow

- [ ] Start app through production composition.
- [ ] Configure/select deterministic providers.
- [ ] Create/select project.
- [ ] Build episode.
- [ ] Build plan.
- [ ] Preflight.
- [ ] Click Generate.
- [ ] Observe monitor progression.
- [ ] Complete generation.
- [ ] Open transcript review.
- [ ] Export from episode library/review.
- [ ] Assert artifact outputs.

---

# R13 — Documentation and compatibility

## DDR-120 — Update user documentation

- [ ] Document concrete provider types and setup.
- [ ] Document model/default precedence.
- [ ] Document research configuration.
- [ ] Document normal TUI generation path.
- [ ] Document Quick Deep Dive overrides.
- [ ] Document CLI generation/control semantics.
- [ ] Document export contents.
- [ ] Document Kitten benchmark output.
- [ ] Document privacy/error-redaction behavior.

## DDR-121 — Update developer architecture documentation

- [ ] Document composition root.
- [ ] Document provider factory.
- [ ] Document shared TUI/CLI service layer.
- [ ] Document run/control lifecycle.
- [ ] Document artifact identity/export contract.
- [ ] Document sanitizer boundary.
- [ ] Document deterministic CI provider strategy.

## DDR-122 — Persisted-data compatibility

- [ ] Test loading existing projects/episodes.
- [ ] Test existing provider configuration records.
- [ ] Add migration/normalization if concrete provider identity requires schema/data change.
- [ ] Reject ambiguous legacy provider entries with actionable guidance when automatic migration is unsafe.
- [ ] Add upgrade-path tests.

---

# R14 — Original TODO requalification

## DDR-130 — Requalify DD-150

- [ ] Source/host/duration/provider/FFmpeg preflight remains correct.
- [ ] Generate action actually starts generation.
- [ ] Episode overrides are honored.
- [ ] Production provider wiring is exercised.

## DDR-131 — Requalify DD-151

- [ ] Generation Monitor uses real production runner.
- [ ] Pause/resume/cancel are real orchestration operations.
- [ ] Transcript and diagnostics actions meet intended semantics.

## DDR-132 — Requalify DD-152

- [ ] Resume actually resumes.
- [ ] Export actually exports.
- [ ] Existing library-state behavior remains correct.

## DDR-133 — Requalify DD-153

- [ ] Targeted regeneration is production-wired.
- [ ] Episode-specific playback is correct.
- [ ] Direct screen tests pass.

## DDR-134 — Requalify DD-154 regressions

- [ ] Playback capabilities remain correct.
- [ ] Headless operation remains graceful.
- [ ] Process cleanup improvements pass.

## DDR-135 — Requalify DD-155

- [ ] Configured defaults override built-ins.
- [ ] Quick Deep Dive reaches actual durable generation/artifacts.

## DDR-136 — Requalify DD-160

- [ ] File source CLI.
- [ ] Directory source CLI.
- [ ] URL source CLI with direct integration test.
- [ ] list/show/include/exclude/remove.
- [ ] JSON output.

## DDR-137 — Requalify DD-161

- [ ] Analyze works.
- [ ] List gaps works.
- [ ] Research selected/all works.
- [ ] Ignore works.
- [ ] Supplemental/candidate outcomes work.

## DDR-138 — Requalify DD-162

- [ ] Preset listing.
- [ ] Host creation.
- [ ] Host editing.
- [ ] Project host listing.
- [ ] Voice/provider assignment.

## DDR-139 — Requalify DD-163

- [ ] Create/configure.
- [ ] Plan through shared service.
- [ ] Show plan.
- [ ] Actual generation.
- [ ] Actual pause/cancel/resume semantics.
- [ ] Status.
- [ ] Actual artifact export.

## DDR-140 — Requalify DD-164

- [ ] Provider list.
- [ ] Real configured-provider health/test.
- [ ] Real model discovery.
- [ ] Real voice discovery.
- [ ] Kitten install/status/actual benchmark.

---

# R15 — Final completion gate

## DDR-150 — Full qualification

- [ ] Full test suite passes.
- [ ] Ruff passes with remediated exclusions.
- [ ] Formatter passes.
- [ ] mypy passes.
- [ ] Build succeeds.
- [ ] Installed-wheel smoke passes.
- [ ] Production-composition integration suite passes.
- [ ] CLI end-to-end acceptance passes.
- [ ] TUI deterministic acceptance passes.
- [ ] Multi-episode isolation matrix passes.
- [ ] Run-state/control matrix passes.
- [ ] Provider-routing matrix passes.
- [ ] Security/redaction matrix passes.
- [ ] Fresh-machine actual generation/export gate passes.
- [ ] Real KittenTTS CPU smoke remains green.
- [ ] No normal-CI dependency on paid credentials/live external services.

## DDR-151 — Documentation and TODO reconciliation

- [ ] User documentation matches final behavior.
- [ ] Developer architecture documentation matches final behavior.
- [ ] Every remediation checkbox has evidence.
- [ ] No known acceptance criterion is silently deferred.
- [ ] Original affected TODO semantics have been requalified.
- [ ] Exact remediation head CI passes.
- [ ] Remediation PR is merged to `master`.
- [ ] Reload this TODO from merged `master`.
- [ ] Exact merged-master CI passes.
- [ ] Only then mark V1 integration remediation complete.
