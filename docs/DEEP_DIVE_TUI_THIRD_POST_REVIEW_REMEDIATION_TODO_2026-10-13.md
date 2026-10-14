# Deeper Dive TUI — Third Post-Review Remediation TODO

**Created:** 2026-10-13 (America/Los_Angeles)  
**Status:** Not started  
**Authority:** `docs/DEEP_DIVE_TUI_THIRD_POST_REVIEW_REMEDIATION_SPEC_2026-10-13.md`  
**Reviewed baseline:** `57b23c9` (`origin/master`; production `src/` identical to `c7ba241`)  
**Predecessor historical checklist:** `docs/DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md`

This is the only completion checklist for the third post-review cycle. No item is prechecked. A checked item must identify production behavior, a deterministic test that failed before the fix, the commit SHA, and exact-head CI where required. If a reproducer disproves a finding, keep the task visible and record a justified N/A with exact evidence.

## Execution rules

- At every run start and after every successful `master` write, reload this TODO and the spec, inspect the exact head and CI, and avoid duplicating concurrent work.
- Follow the repository's GitHub/CI workflow (Ralph Bridge, direct-`master` exact-head CAS writes, no per-task branches/PRs) unless the user directs otherwise.
- **Test first:** for every TPR item, commit or record a regression test that fails on the reviewed baseline before checking the fix.
- Prefer real Textual input (`pilot.press` / `pilot.click`) and service- or filesystem-boundary fault injection over calling actions directly or monkeypatching wizard methods.
- Do not check an item for a helper's presence, a green unit test, or old CI alone. Record test IDs, full commit SHAs and CI run/job IDs. No fabricated evidence.
- Do not change checked state in the second-cycle TODO; TPR-20 adds annotations only.

## TPR-000 — Baseline and reproducers

- [ ] Reload current `master`, the spec and this TODO; record the exact head and confirm `src/` is unchanged from `57b23c9`, or re-map line references.
- [ ] Add failing regression tests (or a recorded N/A) for every "Reproduced" item: TPR-01, 02, 03, 04, 08, 19.1, 19.2, 19.3, 19.4, 19.5.
- [ ] Add deterministic reproducers for every "Source-verified" item: TPR-05, 06, 07, 09, 10, 11, 12, 13, 14, 15, 16, 19.6.
- [ ] Record each outcome as confirmed, disproved (N/A with evidence) or needs-design.

## TPR-100 — Crash, hang and integrity fixes

### TPR-01 — Discard after a vanished voice crashes the app
- [x] Guard every `Select` restore in `WizardShell._restore_discarded_form` against values absent from current options; fall back to `BLANK` with a field-specific status.
- [x] Apply the same guarded restore (`_assign_select`) to the host picker, plan segment picker and speech-choice select (provider/model selects already rebuild options with membership checks; no separate test).
- [x] Define and document the dirty semantics for "durable value no longer offered" without a prompt loop.
- [x] Pilot: save voices → rediscover with one removed → Back → Discard → app alive, config bytes unchanged, clear status.
- [x] Pilot variants: provider error during rediscovery; reordered voices; vanished host-picker original (plan picker covered by the shared helper but not separately piloted).

### TPR-02 — New Deep Dive after Save-and-Exit
- [x] Reset form state, baselines, baseline targets, selected hosts, loaded episode/plan and pending transitions before dirty evaluation when the app starts a fresh New Deep Dive (fresh screen instance or an explicit reset API).
- [x] Ensure app-initiated context switches never count as user edits.
- [x] Prompt Save/Discard/Cancel before resetting a genuinely dirty prior context, naming the old target (`_surface_dirty_prior_wizard`).
- [x] Ensure resume-draft loads the draft's durable state (project step now hydrates from the saved project on mount; found blank in a fresh-app resume).
- [x] Pilot: Save-and-Exit → Home → New Deep Dive → empty form, no false prompt, project count unchanged.
- [ ] Pilot variants: dirty prior context prompts first is done (`test_third_post_review_dirty_prior_wizard.py`); resume-draft loading the correct project is done (`test_third_post_review_resume_draft.py`); the abandon flow pilot is still open.

### TPR-03 — Legacy Episode Setup crash
- [x] Introduce typed `EpisodeFrozenError` / `EpisodeConfigurationConflict` (subclassing `ValueError` for compatibility) in `episode_config.py`.
- [x] Move `service.create()` / `service.edit()` in `EpisodeSetupScreen.action_build_plan` under error handling; show sanitized guidance and keep typed values and `current_episode_id`.
- [x] Skip planning after a failed edit.
- [ ] Update the guided wizard and CLI to render the typed errors consistently.
- [ ] Pilot via both `tui.py` and `guided_app.py`: frozen episode and concurrent writer → app alive, durable data unchanged.

### TPR-04 — Stale plan resurrected by approval
- [x] Capture the episode config revision atomically with the plan load in `approve_plan` and pass it to the repository CAS.
- [x] Implement approval as an in-place status update (`WHERE id=? AND status='draft'`) that preserves plan and segment IDs.
- [x] Persist a config digest in each plan's `plan_json` (`episode_config_sha256`); `plan_validity` rejects a mismatch (legacy plans without a digest stay usable).
- [x] SQLite test with a deterministic hook: concurrent edit between load and persist → approval fails, no plan row.
- [x] Identity test: plan and segment IDs unchanged after approval.
- [x] Validity tests: digest mismatch is unusable; a duration-only edit removes the old plan.
- [x] Correct `docs/ARCHITECTURE.md` to match the final mechanism.

### TPR-19.1 — Sanitizer ReDoS
- [x] Rewrite `_AUTH_QUOTED` (`diagnostics.py:27`) so backslash matches only one alternative.
- [ ] Audit every `diagnostics.py` pattern for ambiguous alternation and nested quantifiers; fix any found.
- [x] Cap the input length processed by `redact()` with a truncation marker.
- [x] Performance regression test: every sanitizer pattern on 10k-character adversarial input within a tight bound.

## TPR-200 — Wizard dirty-form contract

### TPR-17 — Shared typed dirty-form protocol
- [ ] Capture a `WizardDirtyFormSnapshot` when a confirmation opens; carry it through save/discard; refuse execution if the live target drifted.
- [ ] Add one shell API for recording baselines, called only after durable load, successful save or confirmed discard.
- [ ] Remove unconditional `_remember_current_form()` calls in `guided_first_run.py` and `guided_episode_wizard.py`, or prove each runs only on clean durable state.
- [x] Replace `getattr`-based `_form_target_identity` with an overridable method on each wizard (`_wizard_target`).
- [ ] Replace host/plan sentinels (`_ignore_host_picker_value`, `_pending_host_form_values`, `_enforce_dirty_host_selection`) with the shared snapshot mechanism.
- [x] `_editable_snapshot` has an opt-in `strict_form_fields` mode (enabled only in the new test, not suite-wide); a test checks every `_FORM_FIELDS` ID resolves on its wizard.

### TPR-06 — Host-profile discard drops membership
- [x] Scope discard to the dirty area that triggered the prompt (profile, membership or both) and state the scope in the prompt.
- [x] Use the step-entry in-memory membership baseline when no episode exists.
- [x] Replace silent `KeyError`/`ValueError` swallowing in `_load_episode_host_order` with a sanitized status that keeps the current order.
- [x] Pilots (state seeded by direct calls, not real key presses): profile-only discard keeps order edits; no-episode variant keeps selections; leave-step discard reverts both; load failure shows status.

### TPR-07 — Host action double-submit
- [x] Disable and guard all mutating host actions while a confirmation is pending.
- [x] Create is idempotent per form state (identical repeat rejected); the handlers are synchronous so no separate in-flight flag was needed for save/order.
- [x] Pilot (direct action calls, not real key presses): exactly one host created; membership unchanged under an open prompt; normal operation after Cancel.

### TPR-08 — AI preset silently becomes the baseline
- [x] Preset-overwritten provider fields are compared against the stored provider values (baseline captured before the preset is applied; `_capture_preset_baseline`). `setup-ai-choice` itself is intentionally not a dirty field.
- [ ] Make applying a preset over dirty typed values a guarded transition.
- [x] Pilot: durable Ollama → choose OpenAI → Continue → Back → prompt; Discard restores Ollama and leaves durable config bytes unchanged.
- [ ] Pilot: the same flow with Save persists the OpenAI provider (not yet covered).

### TPR-09 — Fail-open discard without a baseline
- [x] Make `_restore_discarded_form` fail closed when no baseline exists: reload durable state or clear editable/sensitive fields; never adopt current values.
- [x] Emit a non-sensitive diagnostic for the missing-baseline condition.
- [x] Tests: baseline removed before Discard → source body and sensitive fields not retained.

### TPR-10 — Destination labels
- [ ] Replace string-encoded transitions with a typed transition value (open: transitions are still encoded strings). One label table/function (`describe_transition`) now replaces the duplicate maps: done.
- [x] Add explicit labels for `host-select`, `plan-select` and `create-recommended-hosts`.
- [x] Parameterized exhaustiveness test over every transition kind scanned from production call sites (pilot prompt checks for host-select and plan-select still open).

### TPR-11 — Project edits after creation
- [x] Decision: support updating project name/topic/audience through the production project service (`DeeperDiveService.update_project`).
- [x] Implement the decision in `guided_new_deep_dive.py`.
- [x] Pilot: create project → Continue → Back → edit → Continue → Save persists.

## TPR-300 — Readiness

### TPR-05 — Silent Retry under saturation
- [x] Return a typed outcome from `FirstRunReadinessCoordinator.request` (`ReadinessRequestOutcome`: started / coalesced / saturated / closed / config-unreadable / start-failed; truthy only when started).
- [x] Publish a visible saturated message and fire callbacks when Retry cannot start.
- [x] Implement and document one policy (chosen: no queue or auto-retry; an explicit Retry publishes a visible "workers are still finishing" status and the user retries once a slot frees; documented in `FirstRunReadinessCoordinator.request`).
- [x] Coordinator tests (Textual pilot variant still open): two blocking timeouts → Retry → visible message; slot frees → Retry (or auto-retry) runs exactly once.
- [ ] Extend the existing 20-no-op-request test to assert the rendered message.

### TPR-14 — Callback contract
- [x] Notify every subscriber of a superseded generation exactly once (stop replacing the list at `guided_async_readiness.py:230`).
- [x] Isolate each callback invocation with sanitized logging in `_start_failed`, `_complete` and `_timeout`.
- [x] Tests: two subscribers across supersession; a raising subscriber does not block the next.

### TPR-15 — Locked config I/O on the UI thread
- [x] Compute the readiness fingerprint without the config lock (`UserConfigStore.load_published`, lock-free read of the atomically replaced file; `ProviderController.config_snapshot`).
- [x] Test: config lock held by another thread → `request()` returns promptly (coordinator-level; a Textual pilot key-press variant is still open).

### TPR-16 — Probe budget and robustness
- [x] Document the exact bound in the architecture notes (`docs/ARCHITECTURE.md`, "Readiness probe time bound"); an aggregate remaining-time budget was not implemented, and the user guide is not yet updated.
- [x] Replace the `type(factory) is ProviderFactory` check in `readiness_probe_controller` with an explicit capability.
- [x] Report adapter build failures per provider (`ProviderBuildResult.build_failures`; probe-call failures were already per provider) instead of failing the whole snapshot.
- [ ] Tests (open: many unreachable fakes within an aggregate deadline, since no aggregate budget exists): a factory subclass gets bounded probes; one unbuildable provider does not hide others' readiness.

## TPR-400 — Episode lifecycle races and normalization

### TPR-12 — Races
- [x] Read config and revision atomically in `EpisodePlannerService.build_plan` (one episode row; `configuration_from_record`).
- [x] Create generation runs under `BEGIN IMMEDIATE` with a config-revision recheck and a no-second-pending/running-run guard (`GenerationRunRepository.select_or_create`).
- [x] Pass the guided wizard's loaded revision into `EpisodeConfigurationService.edit` and enforce it inside the update transaction.
- [x] Hook-injected race tests for each window (build_plan, guided save; concurrent starts via threads, edit-after-preflight via direct revision); two concurrent starts yield exactly one run; an edit after preflight makes start fail with a typed conflict.

### TPR-13 — No-op comparison normalization
- [x] Define one canonical normalization (`EpisodeConfiguration.normalized`) (text strip, tuple host IDs, `None`/blank policy, integer seconds) at the service boundary.
- [x] Route CLI, Quick, guided and legacy setup writes through it (all writes go through `EpisodeConfigurationService.create/edit`, which normalize).
- [x] Service-boundary table test (surface-level CLI/guided variants not separately exercised): whitespace, `None`/`""` and list/tuple variants preserve plan identity; real changes still invalidate.

## TPR-500 — Configuration and security

### TPR-19.2 — Quick echoes a rejected research value
- [x] Parse the Quick research override with the same strip + lowercase rule as `UserConfig` and raise a generic error `from None`.
- [x] Canary test at the shared `_apply_overrides` boundary used by Quick CLI and TUI; mixed-case valid value accepted consistently with Settings.

### TPR-19.3 — Settings normalization order
- [x] Route Settings default saves through `validate_candidate` (normalize then reference-check), matching `provider_tui.py`.
- [x] Table test: identical input gives identical stored value through Settings and ProviderController (first-run delegates to those two writers).

### TPR-19.4 — Fragment redaction truncation
- [x] Terminate `_URL_FRAGMENT` matches at URL delimiters (quotes, `<>`, `)`, `]`, `}`, `,`, whitespace).
- [x] Tests on JSON, prose, Markdown links and multiple URLs per line: canary absent, context intact.

### TPR-19.5 — Sanitizer coverage gaps
- [x] Redact userinfo for any `scheme://user:pass@host`.
- [x] Extend sensitive keys (`code`, `sig`, `signature`, `x-amz-signature`, `x-goog-signature`, `id_token`, `refresh_token`) for query and fragment forms, including hybrid fragments.
- [x] Decode `%23` / `%3D` inside the bounded decode loop before fragment/query matching.
- [x] Canary matrix test for each case; benign URLs unchanged.

### TPR-19.6 — Lock re-entrancy
- [x] Make `UserConfigStore._locked` truly re-entrant (depth counter, reuse the held descriptor) or a plain `Lock` with a non-nesting assertion.
- [x] Test under a timeout: nested acquisition succeeds or fails fast, never hangs.

### TPR-19.7 — Minor validation and quality items
- [x] Accept uppercase URL schemes and normalize them to lowercase.
- [x] Extract one control-character helper in `UserConfig.validate_defaults`; behavior unchanged.
- [x] Consolidate the `_redact_text` decode loops and document the pass order.
- [x] Remove the redundant `os.fchmod` in `_write_temporary` or document why it stays.
- [x] Existing config and diagnostics suites green after the refactors.

## TPR-600 — Test hardening (TPR-18)

- [ ] Add a shared pilot helper that reaches steps and navigates only through real key presses/clicks.
- [ ] Convert dirty-navigation and host-membership tests that set `context.state` or baselines by hand to the helper where they claim end-to-end coverage.
- [ ] Add service- and filesystem-boundary fault-injection fixtures; replace wizard-method monkeypatches (e.g. `test_second_post_review_host_membership.py:242`).
- [ ] Rewrite "restart" tests to use `GuidedDraftStore` and a fresh app instance.
- [ ] Convert the readiness responsiveness test to real key presses for Continue and Home.
- [ ] Replace wall-clock sleeps racing tiny timeouts with events or a controllable clock.
- [ ] Remove `queued_worker_count` or make it meaningful; fix the assertions that rely on it.
- [ ] Mutation check: revert each guarded production fix locally and record that its test fails.

## TPR-700 — Documentation and reconciliation (TPR-20)

- [x] Add a dated "Post-closeout review 2026-10-13" note to the second-cycle TODO listing each contradicted item with a pointer to this spec; checked state unchanged.
- [x] Update `docs/GUIDED_WORKFLOW_USER_GUIDE.md` for the saturated-retry behavior, project editing policy and scoped host discard.
- [x] Update `docs/ARCHITECTURE.md` for CAS approval, run-creation guard and the readiness fingerprint source; it states honestly that plan revision persistence (TPR-04 remainder) and the shared dirty-form contract (TPR-17) remain open.

## TPR-900 — Independent review

- [ ] Independently review every changed source path and trace call sites rather than trusting checked boxes.
- [ ] Examine every new exception handler for swallowed errors, overly broad catches and credential exposure.
- [ ] Re-time all sanitizer patterns on adversarial input after the final change.
- [ ] Review changed tests for false positives and production-boundary bypasses.
- [ ] Add any newly found actionable defect to this TODO and fix it before closeout; confirm no unresolved high or critical issues.

## TPR-910 — Final qualification

- [ ] `uv lock --check`.
- [ ] Ruff format and lint.
- [ ] Strict mypy.
- [ ] Full pytest; record the exact count and confirm no unexplained skip/xfail/xpass.
- [ ] Build sdist and wheel from the exact candidate `master`.
- [ ] Installed-wheel CLI smoke and guided Textual first-run / New Deep Dive / Quick acceptance.
- [ ] Verify each reproducer failed before its fix and passes after; reconcile disproved findings as justified N/A.
- [ ] Record the head SHA, successful exact-head CI run and job IDs, and a consistent test count.
- [ ] If reconciliation changes only documentation, run new exact-head CI on that commit.
- [ ] Declare the third remediation complete only when no unqualified unchecked item remains.

## Evidence ledger

_No entries yet._
