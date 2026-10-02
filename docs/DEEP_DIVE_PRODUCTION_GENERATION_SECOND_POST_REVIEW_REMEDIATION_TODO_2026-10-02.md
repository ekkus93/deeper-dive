# Deeper Dive Production Generation: Second Post-Review Remediation TODO

**Created:** 2026-10-02
**Status:** Open
**Authority:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_SECOND_POST_REVIEW_REMEDIATION_SPEC_2026-10-02.md`
**Predecessor:** `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_TODO_2026-09-27.md`

Checkboxes describe work to be done. Check an implementation item only after production wiring and focused regression evidence exist. Check qualification items only after the exact implementation head is observed in CI. Keep the previous completed checklist unchanged as historical evidence.

## Execution rules

- [ ] Reload this TODO and companion spec from current `master` before implementation and after each merge or direct-master write.
- [ ] Inspect current code, existing focused tests, and CI before duplicating work.
- [ ] Record any discovered change in scope or policy in this spec and TODO before claiming completion.
- [ ] Preserve readable persisted data and route CLI/TUI/background behavior through shared production services.

## SPR-100 — Plan revision and conversation lineage

- [ ] Choose and document the behavior for editing a plan after generation has started: explicit rejection or new generation lineage.
- [ ] Bind durable conversation state, turns, and run resume to the selected plan revision.
- [ ] Apply the policy to whole-plan regeneration, segment regeneration, and segment editing.
- [ ] Handle edits during pending, running, paused, failed, and completed runs deterministically.
- [ ] Prevent old turns, claims, TTS, timeline, or audio from satisfying a revised plan while preserving old run/export history.
- [ ] Preserve shared TTS cache files still referenced by other turns.
- [ ] Add focused partial-run, completed-run, changed-segment-count, and old-run-resume regressions through public services.

## SPR-110 — Provider-originated TUI text

- [ ] Sanitize successful LLM and TTS health messages before status display.
- [ ] Sanitize discovered model identifiers and voice names/IDs before details display.
- [ ] Sanitize provider-originated exceptions on those actions and check shared CLI/preflight surfaces.
- [ ] Add synthetic-secret cases for authorization, Bearer, tokens, client secret, cookie, and credential URLs.
- [ ] Add non-secret model/voice/health text preservation cases.

## SPR-120 — Returned TTS format parity

- [ ] Compare provider-reported format with the requested response format before file, row, or checkpoint persistence.
- [ ] Validate reported WAV content through the existing decoder before durable success where practical.
- [ ] Ensure an unexpected MP3/raw response under a WAV request leaves no successful artifact or final audio.
- [ ] Preserve existing provider, voice, model, cache, legacy artifact, and Kitten WAV behavior.
- [ ] Add CLI/TUI preflight and synthesis regressions for configured MP3 and unexpected returned formats.

## SPR-130 — Role preflight/production parity

- [ ] Make conversation completion checks and host/directing provider resolution follow the same role policy as preflight.
- [ ] Confirm verification role checks match the work the verification stage executes.
- [ ] Cover no plan, partial conversation, completed conversation, revised plan, and new run after completion.
- [ ] Cover missing, unknown, unavailable, and unhealthy provider/model assignments where the role will execute.
- [ ] Confirm CLI/TUI blockers agree and completed conversations do not duplicate turns.

## SPR-140 — Positive duration normalization

- [ ] Reject or resolve infeasible segment counts before duration scaling.
- [ ] Distribute rounding without producing a zero or negative segment duration.
- [ ] Revalidate total and per-segment durations before persisting build, edit, or regeneration output.
- [ ] Add scale-up, scale-down, rounding, many-tiny-segment, and infeasible-target regressions.

## SPR-150 — Strict persisted plan validity

- [ ] Reject scalar, mapping, null, and mixed-type `evidence_ids` and `lead_host_ids` values.
- [ ] Keep valid empty lists, project-scoped evidence, and episode-host membership behavior.
- [ ] Define and enforce row/JSON consistency for title and duration used in generation.
- [ ] Add invalid-shape, corrupt-JSON, cross-project, invalid-host, and auto-planning/blocker regressions.

## SPR-160 — Typing and style cleanup

- [ ] Give the generation-start dependency a typed protocol or explicit application type.
- [ ] Remove obsolete `type: ignore[attr-defined]` from the touched boundary.
- [ ] Remove avoidable broad formatter and import-order suppressions in touched files; explain any remaining narrow exceptions.
- [ ] Run Ruff format, Ruff lint, and mypy without unrelated style churn.

## SPR-170 — Exact-head qualification evidence

- [ ] Document the historical 2026-09-27 final SHA/CI evidence gap accurately without rewriting its completed checklist.
- [ ] Record implementation commit SHA(s), focused test names, and any necessary compatibility decision.
- [ ] Observe exact-head quality and fresh-machine CI on the final implementation commit.
- [ ] Record CI run ID, conclusion, quality result, installed-wheel result, and mandatory Kitten result.
- [ ] Reload this TODO/spec from the qualified `master` head and confirm no unchecked items before declaring completion.

## SPR-180 — Pipeline stage semantics

- [ ] Decide and document whether `sources`, `research`, and `export` produce artifacts during generation or are informational boundaries.
- [ ] Implement real operations and artifact checks, or update progress/status language to match informational behavior.
- [ ] Keep explicit export and multi-episode export isolation behavior intact.
- [ ] Add a production-path status regression for the chosen semantics.

## Qualification matrix

- [ ] Plan revision/resume acceptance, including partial and completed runs.
- [ ] Provider UI redaction matrix with non-secret controls.
- [ ] TTS requested/returned format and no-success-on-mismatch matrix.
- [ ] Preflight versus production role matrix across CLI and TUI.
- [ ] Duration and persisted-plan-shape matrices.
- [ ] Pipeline status semantics and export isolation acceptance.
- [ ] Persisted compatibility checks for projects, plans, runs, turns, timelines, TTS, and exports.
- [ ] `uv lock --check`, Ruff format, Ruff lint, mypy, full pytest, package build, and CLI/import smoke.
- [ ] Installed-wheel fresh-machine and selected real-Kitten qualification on the exact implementation head.

## Closeout evidence

Fill this section only after implementation and qualification. Record exact values, not placeholders marked as completed.

- Implementation SHA(s): pending.
- Named focused tests: pending.
- Final qualified `master` SHA: pending.
- Exact-head CI run ID and conclusion: pending.
- Quality, fresh-machine installed-wheel, and real-Kitten job conclusions: pending.
- Compatibility or intentionally deferred behavior: pending.
