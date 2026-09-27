# Deeper Dive Production Generation Post-Review Remediation Spec

**Created:** 2026-09-27  
**Status:** Ready for implementation  
**Applies to:** post-closeout code review of the production-generation follow-up on `master`  
**Companion checklist:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_TODO_2026-09-27.md`  
**Primary objective:** fix every confirmed functional, security, architecture, acceptance, and maintainability issue identified by the 2026-09-27 post-review without regressing the production-generation behavior already qualified on `master`.

---

## 1. Background

The prior production-generation follow-up materially improved Deeper Dive: configured provider routing, durable run state, evidence-scoped generation, per-turn TTS artifact identity, valid WAV composition, CLI/TUI acceptance tests, installed-wheel qualification, and same-session provider refresh all exist.

The post-closeout review found several places where the checked TODO states a stronger invariant than the code actually provides, plus one major product-level defect outside the literal previous checklist: production conversation generation currently creates one host turn and then treats conversation generation as complete.

This remediation is additive. Do not rewrite the previous completed TODO to hide the review. The prior file remains historical evidence; this spec and its companion TODO are the new source of truth for the review findings.

---

## 2. Findings in scope

The remediation must address all of these findings:

1. Production conversation generation emits only one host turn regardless of segment count or episode target.
2. `DirectorDecision.segment_signal` is not used to progress or complete segments/episodes.
3. Any existing turn causes the conversation stage to skip entirely.
4. Provider saves persist config before the candidate runtime is successfully built, so a failed save can poison durable configuration.
5. Generation preflight can omit configured `directing` and `verification` roles even though production later executes them.
6. Custom/injected provider controllers can diverge from `ProductionComposition.providers`.
7. Local/remote provider classification is duplicated across code paths.
8. Planning skips whenever any plan row exists rather than when a valid usable plan exists.
9. Segment edit/regeneration can disable evidence validation because an empty allowed-evidence set means “do not validate”.
10. Some execution-time assignment/configuration failures occur outside durable pipeline failure handling.
11. Export metadata uses a narrower secret filter than the canonical sanitizer.
12. Secret-bearing keys such as `access_token`, `refresh_token`, `client_secret`, and cookies are not guaranteed to be removed from exports.
13. Provider health/discovery/status text is not uniformly sanitized before presentation.
14. OpenAI-compatible TTS can generate MP3 while the production composition stage is WAV-only.
15. Preflight can therefore report Ready for a configuration guaranteed to fail after TTS work.
16. TTS result identity validates provider and voice but not an explicitly requested model.
17. WAV resampling uses nearest-neighbor interpolation, which is a poor production audio-quality choice.
18. Transcript repair can leave obsolete physical TTS cache files.
19. Production code discovers composition through private `service._production_composition` state.
20. Transcript repair imports private stage functions.
21. Broad `fmt`, Ruff, and `type: ignore[attr-defined]` escape hatches mask the composition/API problem.
22. `EpisodeExporter.write_mp3()` calls a private FFmpeg-composer method.
23. Some review/export paths duplicate raw SQL instead of shared repository/service logic.
24. The reusable follow-up fixture seeds an approved plan directly rather than planning through `EpisodePlannerService`.
25. The fixture is not reused for the multi-episode isolation gate despite the earlier checklist claim.
26. Some acceptance tests therefore prove a seeded state instead of the complete production path.
27. Mandatory CI currently performs a real external KittenTTS install/download; documentation must accurately classify that external dependency.
28. Existing redaction tests do not cover the newly identified export-key and health-message cases.
29. Production transcript repair uses no-op recheck and summary-update collaborators.

---

## 3. Non-negotiable design principles

- CLI, TUI, background generation, repair, and tests must converge on shared production services.
- Once a generation run exists, execution failures must be represented durably.
- Preflight must reject configurations that production is guaranteed to reject.
- One canonical recursive sanitizer must define credential redaction everywhere.
- Fake providers are permitted for deterministic testing only through normal provider configuration/factory/registry boundaries.
- Durable artifact identity must include all synthesis inputs that can change output.
- Acceptance fixtures must exercise public production services rather than bypassing the behavior under test.
- Compatibility with existing user config, projects, episodes, runs, turns, timelines, and TTS artifacts must be preserved unless an explicit tested migration is necessary.
- A green generic test suite is not sufficient evidence if a specific acceptance contract below is not exercised.

---

## 4. Multi-turn and multi-segment conversation generation

### 4.1 Replace single-turn production behavior

Introduce a public conversation-generation service that progresses a durable episode through its plan.

For each episode it must:

1. load the selected valid plan and ordered segments;
2. load or initialize durable `ConversationState`;
3. determine the current incomplete segment/turn unit;
4. resolve configured directing and host-generation providers through the production runtime;
5. obtain a bounded director decision;
6. generate exactly one next host turn;
7. validate participating host and evidence scope;
8. atomically persist turn text, evidence IDs, provider/model identity, conversation state, and generation unit checkpoint;
9. repeat until the episode is complete or a safety bound is reached.

The existence of one prior turn must not imply that the stage is complete.

### 4.2 Completion signals

Production must honor:

- `CONTINUE`: remain in the current segment;
- `COMPLETE_SEGMENT`: persist completion/advance to the next segment;
- `COMPLETE_EPISODE`: terminate conversation generation cleanly.

If directing is intentionally unassigned, define a deterministic bounded fallback policy. The fallback must still advance and terminate predictably.

### 4.3 Safety bounds

Define and test:

- maximum turns per segment;
- maximum turns per episode;
- how target words/duration participate in the bound;
- behavior when a provider never emits completion;
- early completion behavior;
- single-host and multi-host behavior;
- multi-segment behavior;
- resume after interruption or provider failure.

A broken provider must not create an infinite generation loop.

### 4.4 Resume/idempotency

Resume must continue from the first incomplete durable unit. Previously committed turns must retain identity and content. No completed turn may be duplicated because the process restarted, the run was paused, or a later provider call failed.

---

## 5. Transactional provider configuration

### 5.1 Candidate-build transaction

Provider save/edit must follow this ordering:

1. load current durable config;
2. create candidate updated config in memory;
3. validate candidate provider fields;
4. build the complete candidate `ProviderBuildResult`;
5. only after successful build, persist the candidate config atomically;
6. publish/swap the candidate runtime;
7. refresh dependent preflight/runtime accessors.

If any step before persistence fails, both durable config and live runtime must remain unchanged.

This must cover missing credential environment variables, missing base URLs, missing voice catalogs, unsupported adapters, invalid formats, and other provider-factory failures.

### 5.2 Removal transaction

Provider removal must use the same candidate-build semantics. A failed removal must not leave config and runtime out of sync.

### 5.3 One runtime owner

There must be one typed provider-runtime owner shared by provider health/discovery, preflight, planning, directing, host generation, verification, repair, and TTS.

Attaching or injecting a provider controller must synchronize immediately; it must not merely install a callback for future reloads while leaving a stale `ProductionComposition.providers` snapshot.

### 5.4 Central locality policy

Move local/remote classification to one shared policy. Explicit `network_scope` must override inferred adapter defaults. CLI/TUI/preflight must use the same result.

---

## 6. Complete preflight and durable failures

### 6.1 Production role derivation

Preflight must validate the actual model roles the selected episode will execute:

- `episode_planning` when no valid plan exists;
- `host_generation` whenever conversation work remains;
- `directing` when configured and production will call it;
- `verification` when configured and production will call it.

The design must be extensible if research/source roles later enter the generation path.

For each executed role, preflight must detect missing assignment, unknown provider, unavailable model, unhealthy provider, and local-only violations.

### 6.2 Durable execution boundary

Pre-run preflight may block without creating a run. Once a run exists, configuration/provider/assignment errors encountered during execution must update the run to `failed` with stage, stable failure code, sanitized message, and timestamp.

Do not allow an existing run to remain misleadingly `pending` or `running` because an exception occurred before the orchestrator's failure path.

---

## 7. Valid-plan and evidence integrity

### 7.1 Valid plan definition

A plan is usable only when:

- it belongs to the selected episode;
- it has at least one segment;
- persisted JSON is parseable;
- segment ordinals are coherent;
- titles are non-empty;
- durations are positive;
- lead hosts belong to the episode;
- evidence IDs satisfy project/episode scope;
- status is allowed by the generation approval policy.

The planning stage may skip only a valid usable plan. Empty, corrupt, semantically invalid, or disallowed-state plans must not suppress auto-planning.

### 7.2 Evidence validation API

Remove the “empty set disables validation” ambiguity.

Use an explicit representation such as `allowed_evidence: set[str] | None`, where `None` means validation intentionally unavailable and an empty set means no evidence IDs are valid.

`regenerate_segment()` and `edit_segment()` must reject nonexistent or cross-project evidence IDs.

---

## 8. Canonical security/redaction boundary

### 8.1 One sanitizer

Use one recursive sanitizer for:

- persisted pipeline failures;
- diagnostics and structured logs;
- CLI-visible errors;
- TUI-visible errors/status;
- provider health/model/voice messages;
- export metadata;
- future diagnostic bundles.

It must cover representative names including authorization, API-key variants, token, access token, refresh token, secret, client secret, password, and cookie variants.

It must preserve free-form Bearer redaction, assignment redaction, quoted-map redaction, URL credential redaction, nested collection handling, and exception cause/context sanitization.

### 8.2 Export metadata

Remove the independent secret vocabulary in `EpisodeExporter.write_metadata()`. Sanitize recursively with the canonical API immediately before serialization.

### 8.3 Provider-originated status text

Assume provider health/discovery messages may contain credentials. Sanitize them before presentation or persistence.

### 8.4 Credential persistence

Continue storing only credential references such as environment-variable names. Transaction rollback tests must prove failed saves do not introduce secret values or invalid durable provider entries.

---

## 9. TTS and audio correctness

### 9.1 Composition-compatible format preflight

Choose and document one policy:

**A. WAV-only production composition:** reject non-WAV selected TTS response formats in preflight before any expensive generation; or

**B. Multi-format production composition:** add a public decoder/transcoder path for explicitly supported compressed/container formats such as MP3.

It is not acceptable for preflight to report Ready when successful TTS output is guaranteed to fail composition.

### 9.2 Returned TTS identity

Before saving a successful artifact validate:

- returned provider against requested provider;
- returned voice against requested voice;
- returned model against explicitly requested model;
- returned/stored format consistency;
- non-empty audio.

If an adapter cannot report model identity, define that behavior explicitly for the adapter rather than silently accepting mismatches.

### 9.3 Resampling quality

Replace nearest-neighbor production resampling with FFmpeg/libswresample or another production-quality deterministic resampler. Preserve the canonical output contract unless deliberately revised.

Tests should verify format/rate/channel/duration behavior without relying on exact resampled PCM across runtime versions.

### 9.4 Public FFmpeg API

`EpisodeExporter` must not call a private `FFmpegComposer._run()` method. Expose a public conversion/transcode operation or a dedicated audio export service.

### 9.5 Reference-aware cache cleanup

When transcript repair invalidates TTS:

- retain a physical artifact that is still referenced by another turn;
- delete or deterministically garbage-collect unreferenced obsolete files;
- invalidate affected timeline/final audio;
- regenerate/reuse only the correct current cache identity.

---

## 10. Transcript repair correctness

Production transcript repair must not use permanent no-op recheck or summary-update implementations.

After changing a turn:

1. preserve unaffected turns;
2. clear stale claim/verification state for changed text;
3. re-run the real claim extraction/verification/recheck path used by current architecture;
4. update conversation summary/context if required;
5. invalidate affected TTS/timeline/final audio safely;
6. regenerate audio through public production service methods;
7. sanitize provider/runtime failures before UI display.

Private imports of `_tts_stage` and `_composition_stage` from the TUI/review layer must be removed.

---

## 11. Explicit composition architecture

`ProductionComposition` must be an explicit typed application dependency, not hidden in `DeeperDiveService._production_composition`.

Required outcomes:

- TUI owns or receives a typed composition/application context;
- controllers receive the dependencies they need explicitly;
- production code stops using `getattr(service, "_production_composition", ...)`;
- tests stop reaching through `app.service._production_composition`;
- private stage functions are replaced by public service operations where cross-module access is required;
- unnecessary `type: ignore[attr-defined]` suppressions disappear.

Keep `DeeperDiveService` a service/repository facade rather than a service locator.

Where touched by this remediation, reduce avoidable broad `# fmt: off`, import-order suppressions, and duplicated raw SQL if an existing repository/service boundary can express the same operation cleanly.

This is not permission for unrelated repository-wide style churn.

---

## 12. Deterministic acceptance fixture

Create one reusable fixture/builder family that uses public production services to create:

- durable provider configuration;
- indexed corpus;
- host(s) and TTS assignment;
- episode configuration;
- model-role assignments;
- an episode plan created through `EpisodePlannerService` or the public planning entry point;
- evidence scope;
- generation run;
- multiple turns where the plan requires them;
- TTS artifacts;
- timeline/final audio;
- exportable transcript/manifest/metadata/audio.

Normal acceptance setup must not seed an approved plan directly through repository writes. Direct DB/repository seeding remains acceptable only for compatibility/migration tests whose explicit purpose is emulating legacy state.

Reuse this fixture family for:

- CLI planning/generation/status/export;
- TUI provider save/reload/preflight/generate/monitor/review/library/export;
- duplicate start and pause/resume/cancel;
- multi-episode isolation;
- evidence/provenance;
- TTS cache identity/invalidation;
- installed-wheel acceptance where practical.

At least one CLI `episode generate` acceptance must begin with no plan and prove that auto-planning uses the configured `episode_planning` provider.

---

## 13. CI and qualification policy

Mandatory deterministic quality gates must not require paid credentials, cloud-provider availability, or a GPU.

The existing fresh-machine workflow downloads and installs a real KittenTTS runtime from an external source. Choose and document one policy:

1. keep it mandatory and explicitly classify fresh-machine qualification as external-network dependent; or
2. move real KittenTTS into a separate opt-in/scheduled qualification workflow while preserving deterministic mandatory fake/local TTS coverage.

Do not claim mandatory CI is free of live external dependencies if mandatory CI downloads external runtime assets.

Final qualification must include:

- `uv lock --check`;
- Ruff format;
- Ruff lint;
- mypy;
- full pytest;
- package build;
- CLI/import smoke;
- multi-turn/multi-segment conversation matrix;
- provider transaction/runtime matrix;
- role/preflight matrix;
- plan/evidence matrix;
- security/redaction matrix;
- TTS format/identity/cache matrix;
- transcript repair matrix;
- CLI acceptance;
- TUI acceptance;
- multi-episode isolation;
- installed-wheel fresh-machine acceptance;
- the chosen real-Kitten qualification gate.

---

## 14. Compatibility requirements

Preserve readability/behavior for:

- current user-config schema;
- existing concrete provider records;
- existing projects/episodes;
- generation runs;
- conversation turns/provider-identity rows;
- canonical `complete` TTS artifacts;
- legacy readable `completed` TTS artifacts;
- audio timelines;
- existing exports.

Any required migration must be idempotent, tested with representative legacy rows, and failure-safe.

---

## 15. Documentation requirements

Update user/developer documentation to describe only implemented behavior:

- multi-turn/multi-segment generation;
- completion signals and safety bounds;
- transactional provider saves/removal;
- exact model-role preflight policy;
- valid-plan rules;
- evidence validation on plan edits/regeneration;
- TTS/composition format compatibility;
- canonical redaction guarantees;
- transcript repair reverification/audio regeneration;
- reference-aware cache cleanup;
- explicit composition ownership;
- mandatory versus external KittenTTS qualification policy.

---

## 16. Final acceptance criteria

This remediation is complete only when:

1. production conversation generation is bounded, resumable, multi-turn, and multi-segment;
2. segment/episode completion signals work and are durable;
3. provider save/edit/remove is transactional;
4. every production-executed configured model role is validated before generation;
5. invalid plans do not suppress planning;
6. plan edit/regeneration cannot persist out-of-scope evidence;
7. post-run execution errors produce durable failed state;
8. one canonical sanitizer protects diagnostics, statuses, and export metadata;
9. non-WAV TTS is either supported in composition or rejected by preflight before synthesis;
10. returned TTS model identity cannot silently disagree with the requested model;
11. transcript repair performs real reverification/update work and uses public audio-regeneration APIs;
12. stale physical TTS artifacts are cleaned without deleting shared live cache files;
13. production resampling is audio-quality appropriate;
14. hidden `service._production_composition` and private-stage coupling is removed from production paths;
15. the shared fixture builds plans through public production services and is reused by the required acceptance gates;
16. CI documentation accurately describes external dependencies;
17. exact remediation-head CI passes;
18. all TODO tasks are reconciled with specific test/CI evidence;
19. completed work is present on `master`;
20. the TODO reloaded from current `master` has zero unchecked items;
21. exact current-`master` CI passes.

---

## 17. Required closeout evidence

The companion TODO closeout must record:

- implementation commit SHA(s);
- PR numbers only when Ralph Bridge policy required them;
- exact-head CI run ID/conclusion;
- current/final `master` SHA;
- current/final `master` CI run ID/conclusion;
- named tests covering every remediation cluster;
- any intentionally deferred behavior in a separate explicit follow-up spec/TODO.

Do not declare the remediation complete solely because generic CI is green.
