# Deeper Dive Production Generation: Second Post-Review Remediation Spec

**Created:** 2026-10-02
**Status:** Complete; implementation and exact-head qualification recorded in companion TODO
**Applies to:** `master` at `7675d07dc615c49cc13c3ca16d21b98156f69f63`
**Companion checklist:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-02.md`
**Predecessor:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_TODO_2026-09-27.md`

This spec records findings from a static review of the completed 2026-09-27 remediation. It does not change the historical checklist or assert that a proposed failure has already been reproduced at runtime. The implementation must prove each contract below with focused regression coverage and then qualify the resulting head.

## 1. Findings and scope

| ID | Priority | Finding | Current code |
| --- | --- | --- | --- |
| SPR-100 | High | Plan edits and regeneration leave durable conversation progress and turns associated with the previous plan. | `episode_planner.py`, `conversation_generation.py`, `plan_validity.py` |
| SPR-110 | High | Provider health, model, and voice discovery text reaches the TUI without canonical redaction. | `providers_screen.py` |
| SPR-120 | Medium | TTS accepts a returned format different from the requested WAV format and can persist an artifact composition will reject. | `tts_generation.py`, `composition.py` |
| SPR-130 | Medium | A completed conversation can omit host generation from preflight while the conversation stage still resolves that role. | `generation_start.py`, `composition.py` |
| SPR-140 | Medium | Plan duration scaling can produce a zero or negative final segment. | `episode_planner.py` |
| SPR-150 | Medium | Persisted plan validation treats malformed evidence and lead-host field types as empty collections. | `plan_validity.py` |
| SPR-160 | Maintenance | Broad formatter/import suppressions and obsolete attribute ignores remain in code touched by the prior remediation. | `generation_start.py`, `conversation_generation.py`, `provider_tui.py`, `providers_screen.py`, `export.py`, `episode_library_export.py` |
| SPR-170 | Evidence | The previous checklist checks off final current-master qualification but records placeholders instead of a final SHA and CI run. | 2026-09-27 TODO closeout |

The review also found production pipeline stage labels for `sources`, `research`, and `export` mapped to a no-op handler. SPR-180 requires an explicit product contract for these labels so progress and completion do not imply artifacts that were never produced. This is an architecture review item, not a claim that those stages were promised to generate content in the prior spec.

## 2. Shared implementation rules

- Keep the prior completed checklist intact as historical evidence. Use this pair as the source of truth for the new work.
- Use public production services for CLI, TUI, background generation, repair, and acceptance coverage. Keep deterministic fake providers behind the normal config/factory/registry boundary.
- Preserve readable existing projects, plans, runs, turns, timelines, TTS artifacts, and exports. Add a migration only if a documented compatibility case requires it.
- Once a generation run exists, execution errors must end in a durable failed state with a sanitized message. Preflight may block before run creation.
- Tests must assert externally observable behavior and durable state, including a negative case for each bug. A class or helper existing is insufficient evidence.
- Do not mark this remediation complete from an older CI run or from the presence of unchecked tests alone.

## 3. SPR-100: plan revision and conversation lineage

Define a plan revision identity that changes when a plan or any segment affecting generation changes. A regenerated plan, regenerated segment, and edited segment must each follow the same rule. Approval alone may retain the revision when content is unchanged.

Before persisting a revision, determine whether the episode has generated turns or conversation progress. Use one documented policy: either reject edits to a started episode and require an explicit new generation operation, or atomically create a new generation lineage and invalidate dependent work. If regeneration is supported, it must preserve the old run's historical output while ensuring the new run cannot reuse old state, turns, claims, TTS, timeline, or audio as if they belonged to the new plan. Do not delete shared cache files still referenced by another turn.

The selected plan identity and revision must be checked when resuming a run. A run that started against one revision must not silently consume another revision. A completed state for an old revision must not make a new revision appear complete. A plan edit during an active run must have deterministic behavior, including a clear error or explicit cancellation/restart boundary.

Acceptance cases: edit and regenerate before first generation; edit after a partially completed segment; edit after a completed episode; regenerate a segment with unchanged segment count; regenerate a plan with fewer or more segments; resume an old run after a revision; preserve prior run/export history; confirm no old turn or audio is attributed to the revised plan.

## 4. SPR-110: provider-originated UI sanitization

Apply the canonical recursive sanitizer at the presentation boundary to provider health messages, discovered model identifiers and display values, discovered voice IDs and names, and provider-originated exceptions. Keep useful non-secret text visible. Cover both LLM and TTS branches and every place the Providers screen writes a status or details widget. Avoid scattering a second secret vocabulary through the UI.

Acceptance cases: synthetic `Authorization`, Bearer, `access_token`, `refresh_token`, `client_secret`, cookie, and credential URL values in successful health/discovery responses and exceptions; assert the secret is absent and `[REDACTED]` appears. Also assert ordinary model and voice names remain legible. Check CLI/preflight parity for shared provider text where those surfaces expose it.

## 5. SPR-120: returned TTS format parity

Construct the requested response format once and compare it with the provider-reported format before writing bytes, a success row, or a TTS checkpoint. Production composition remains WAV-only unless a separately specified multi-format change is made. A successful provider response reported as MP3, raw PCM, or another format for a WAV request is an identity mismatch. Validate media type and actual container where practical so a `.wav` suffix cannot mask MP3 bytes; FFmpeg normalization remains the final content decoder. Preserve provider/model/voice identity checks and existing readable legacy artifacts.

Acceptance cases: requested WAV/returned MP3; requested WAV/reported WAV with non-WAV bytes; requested WAV/valid WAV; explicitly configured MP3 blocked before synthesis by CLI and TUI preflight; mismatch leaves no success artifact, checkpoint, or final audio. Existing model identity and cache reuse cases must continue to pass.

## 6. SPR-130: role preflight and production parity

Derive required roles from the work the production stages will actually execute. The conversation stage must check plan/conversation completion before resolving host or directing providers, or preflight must require those roles for any run that still resolves them. Apply the same principle to verification. Do not report Ready for a configuration that will fail solely because a stage resolves an omitted role.

Acceptance cases: no plan; partial conversation; completed conversation with host assignment present, missing, or invalid; configured directing/verification roles; a new run after a completed run; invalidated plan revision; CLI and TUI routes and blockers agree. Confirm a completed conversation does not create duplicate turns.

## 7. SPR-140: feasible positive segment durations

The planner must never persist a segment with duration below one second. Check feasibility before scaling: an episode target in whole seconds cannot support more one-second-minimum segments than target seconds. Handle infeasible generator output with a stable, actionable planning error or a documented bounded reduction that preserves intended ordering. Distribute rounding residuals without making any segment nonpositive. Revalidate the final normalized segments before persistence.

Acceptance cases: ordinary scale-up and scale-down; rounding in both directions; many tiny segments near the target; segment count exceeding target seconds; targeted regeneration/edit that changes the duration distribution. Verify total duration and every persisted segment duration.

## 8. SPR-150: strict persisted plan shape

The shared validity policy must reject malformed `evidence_ids` and `lead_host_ids` types, including strings, mappings, null, and mixed non-string members. Validate the same shape used by planning and conversation generation. A valid list may be empty; a malformed value cannot be interpreted as an empty list. Keep cross-project evidence and non-member host rejection. Reject a plan before generation if row and JSON values disagree on fields that drive generation, or define a single authoritative representation and validate against it.

Acceptance cases: valid empty lists; valid scoped IDs; scalar, mapping, null, and mixed-type values; row/JSON title or duration disagreement; corrupt JSON; cross-project evidence; invalid host. Confirm invalid plans trigger auto-planning or an actionable blocker according to the existing plan policy.

## 9. SPR-160: typing and style cleanup

Replace `object` plus `type: ignore[attr-defined]` in generation-start boundaries with a typed protocol or explicit application dependency. Remove formatter and import-order suppressions from the files touched by this remediation where formatting/import order can be made valid without broad churn. Retain a narrowly justified suppression only with an adjacent explanation. Do not make unrelated formatting changes. Run formatter, Ruff, and mypy after cleanup.

## 10. SPR-170: qualification evidence reconciliation

Do not retroactively assert that a historical CI run covered a later commit. Record the exact implementation SHA, the CI run ID and conclusion for that SHA, and the quality and fresh-machine job conclusions. If the mandatory Kitten gate remains part of fresh-machine CI, include its result. State clearly if the preexisting 2026-09-27 checklist's final evidence cannot be reconstructed; leave that historical text intact and record the limitation here. The current `master` at review time is `7675d07dc615c49cc13c3ca16d21b98156f69f63`; subsequent commits need their own exact-head evidence.

## 11. SPR-180: pipeline stage semantics

Decide whether `sources`, `research`, and `export` are real generation stages or informational boundaries. If they are real stages, give each a production operation and durable artifact validity check. If they are informational, change progress/status wording so a completed checkpoint does not claim source processing, research, or export artifacts were produced. Keep explicit CLI/TUI export behavior and existing export isolation intact. Add one acceptance case proving the chosen semantics to a user of generation status.

## 12. Qualification and closeout

Required focused regression groups: plan revision and resume; provider UI secrets; TTS format identity; role routing; duration normalization; persisted plan shape; pipeline status semantics. Reuse the public production acceptance fixture where it helps exercise real wiring. Run lock, format, lint, mypy, full pytest, package build, CLI/import smoke, installed-wheel fresh-machine workflow, and the selected real-Kitten qualification gate on the final implementation head.

Completion requires all TODO items checked with named tests and exact-head CI evidence, no open high or medium finding above, no compatibility regression, and a final reread of this spec and its TODO from the qualified `master` commit.

## Implementation decisions (2026-10-02)

- The current checklist uses SPR-100–180, superseding the predecessor R4–R15
  execution grouping for this remediation.
- Plan edits after generation starts are explicitly rejected. A persisted plan is
  frozen when any run (including pending, failed, cancelled, or completed), durable
  conversation state, or turns exist. Create a new episode to generate revised
  content. Initial automatic planning remains available when a run has no plan.
  Before generation, every edit/regeneration creates a new plan ID as the revision
  identity. Unchanged approval preserves plan and segment identities. Conversation
  state, turns, and resume stay bound to the frozen episode plan; no dependent
  artifacts or cache references are removed. Repository replacement rechecks this
  contract in its persistence transaction. Runs also store a content fingerprint
  in durable plan-revision units; resume checks it independently and rejects
  out-of-band drift. Legacy runs acquire this binding on first observation.
- Persisted segment rows are authoritative for title and duration. Present JSON
  values must agree exactly; omitted legacy fields still use the row. Missing ID
  lists retain legacy empty-list behavior; explicit null, scalar, mapping, or mixed
  members are rejected. Generator ID lists use the same strict rule.
- Duration scaling reserves one second per segment and allocates remaining whole
  seconds by integer largest remainder. More segments than target seconds fail
  before persistence. The existing 10% duration tolerance remains unchanged.
- Production synthesis is WAV-only, matching composition and preflight. Reported
  format, media type, RIFF/WAVE container, and existing FFmpeg decoder must pass
  before writing successful audio, a row, or a checkpoint. Legacy cached artifacts
  remain readable; this does not rewrite historical files.
- Completed conversation skips host/directing resolution and creates no duplicate
  turns. Configured verification remains required because production verifies the
  existing transcript on a new run. Directing is required only for remaining
  conversation work.
- Sources, research, and export checkpoints are informational boundaries. Generation
  consumes already-indexed sources/evidence and composes audio; explicit export
  creates export artifacts. Progress messages, CLI stage descriptions, and monitor
  labels state these semantics while preserving persisted stage keys.
- The predecessor's placeholder closeout cannot establish exact-head qualification
  of its final reconciled commit. Its completed checklist is preserved unchanged;
  this remediation requires new exact-head CI evidence and does not infer coverage
  from an earlier passing run.

Implementation `e5b62c8f98ec7c2eecd05daf6327fd681c8ae0d0` passed exact-head CI
run `37068864649`, including quality, installed-wheel fresh-machine acceptance, and
mandatory real KittenTTS Micro CPU smoke. The companion TODO records the named
regressions, compatibility decisions, and observed job results. The documentation
closeout is independently qualified before completion is reported.
