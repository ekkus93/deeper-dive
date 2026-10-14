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
- [ ] Apply the same guarded restore to the host picker, plan segment picker and provider/model selects.
- [x] Define and document the dirty semantics for "durable value no longer offered" without a prompt loop.
- [x] Pilot: save voices → rediscover with one removed → Back → Discard → app alive, config bytes unchanged, clear status.
- [ ] Pilot variants: provider error during rediscovery; reordered voices.

### TPR-02 — New Deep Dive after Save-and-Exit
- [x] Reset form state, baselines, baseline targets, selected hosts, loaded episode/plan and pending transitions before dirty evaluation when the app starts a fresh New Deep Dive (fresh screen instance or an explicit reset API).
- [x] Ensure app-initiated context switches never count as user edits.
- [ ] Prompt Save/Discard/Cancel before resetting a genuinely dirty prior context, naming the old target.
- [ ] Ensure resume-draft loads the draft's durable state, not stale widget contents.
- [x] Pilot: Save-and-Exit → Home → New Deep Dive → empty form, no false prompt, project count unchanged.
- [ ] Pilot variants: abandon flow; dirty prior context prompts first; resume-draft loads the correct project.

### TPR-03 — Legacy Episode Setup crash
- [x] Introduce typed `EpisodeFrozenError` / `EpisodeConfigurationConflict` (subclassing `ValueError` for compatibility) in `episode_config.py`.
- [x] Move `service.create()` / `service.edit()` in `EpisodeSetupScreen.action_build_plan` under error handling; show sanitized guidance and keep typed values and `current_episode_id`.
- [x] Skip planning after a failed edit.
- [ ] Update the guided wizard and CLI to render the typed errors consistently.
- [ ] Pilot via both `tui.py` and `guided_app.py`: frozen episode and concurrent writer → app alive, durable data unchanged.

### TPR-04 — Stale plan resurrected by approval
- [x] Capture the episode config revision atomically with the plan load in `approve_plan` and pass it to the repository CAS.
- [x] Implement approval as an in-place status update (`WHERE id=? AND status='draft'`) that preserves plan and segment IDs.
- [ ] Persist a config revision/hash with each plan; make `plan_validity` detect any stale-input plan.
- [x] SQLite test with a deterministic hook: concurrent edit between load and persist → approval fails, no plan row.
- [x] Identity test: plan and segment IDs unchanged after approval.
- [ ] Validity test: duration-only edit marks the old plan stale.
- [ ] Correct `docs/ARCHITECTURE.md` lines 189-191 to match the final mechanism.

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
- [ ] Replace `getattr`-based `_form_target_identity` with an overridable method on each wizard.
- [ ] Replace host/plan sentinels (`_ignore_host_picker_value`, `_pending_host_form_values`, `_enforce_dirty_host_selection`) with the shared snapshot mechanism.
- [ ] Make `_editable_snapshot` fail loudly in tests for missing widgets; add a test that every `_FORM_FIELDS` ID resolves on its step.

### TPR-06 — Host-profile discard drops membership
- [ ] Scope discard to the dirty area that triggered the prompt (profile, membership or both) and state the scope in the prompt.
- [ ] Use the step-entry in-memory membership baseline when no episode exists.
- [ ] Replace silent `KeyError`/`ValueError` swallowing in `_load_episode_host_order` with a sanitized status that keeps the current order.
- [ ] Pilots: profile-only discard keeps order edits; no-episode variant keeps selections; leave-step discard reverts both; load failure shows status.

### TPR-07 — Host action double-submit
- [ ] Disable and guard all mutating host actions while a confirmation is pending.
- [ ] Add in-flight single-shot guards for create/save/order actions; make create idempotent per interaction.
- [ ] Pilot with repeated key presses/clicks: exactly one host created; membership unchanged under an open prompt; normal operation after Cancel.

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
- [ ] Replace string-encoded transitions with a typed transition value and one label function; delete the duplicate map.
- [ ] Add explicit labels for `host-select`, `plan-select` and `create-recommended-hosts`.
- [ ] Parameterized exhaustiveness test over every transition kind; pilot prompt checks for host-select and plan-select.

### TPR-11 — Project edits after creation
- [ ] Decide: support updating project name/topic/audience through the production project service, or make the fields read-only after creation with an explanation.
- [ ] Implement the decision in `guided_new_deep_dive.py`.
- [ ] Pilot: create project → Back → edit → Continue → Save persists (or no prompt for read-only fields).

## TPR-300 — Readiness

### TPR-05 — Silent Retry under saturation
- [ ] Return a typed outcome from `FirstRunReadinessCoordinator.request` (started / coalesced / saturated / closed).
- [x] Publish a visible saturated message and fire callbacks when Retry cannot start.
- [x] Implement and document one policy (chosen: no queue or auto-retry; an explicit Retry publishes a visible "workers are still finishing" status and the user retries once a slot frees; documented in `FirstRunReadinessCoordinator.request`).
- [ ] Coordinator test and Textual pilot: two blocking timeouts → Retry → visible message; slot frees → Retry (or auto-retry) runs exactly once.
- [ ] Extend the existing 20-no-op-request test to assert the rendered message.

### TPR-14 — Callback contract
- [ ] Notify every subscriber of a superseded generation exactly once (stop replacing the list at `guided_async_readiness.py:230`).
- [ ] Isolate each callback invocation with sanitized logging in `_start_failed`, `_complete` and `_timeout`.
- [ ] Tests: two subscribers across supersession; a raising subscriber does not block the next.

### TPR-15 — Locked config I/O on the UI thread
- [ ] Compute the readiness fingerprint from an in-memory snapshot published on config commit (or load off-thread).
- [ ] Test: config lock held by another thread → `request()` returns promptly and a pilot key press is processed.

### TPR-16 — Probe budget and robustness
- [ ] Enforce an aggregate remaining-time budget across sequential probe calls, or document the exact bound in the user guide and architecture notes.
- [ ] Replace the `type(factory) is ProviderFactory` check in `readiness_probe_controller` with an explicit capability.
- [ ] Report adapter build/probe failures per provider instead of failing the whole snapshot.
- [ ] Tests: many unreachable fakes finish within the aggregate deadline; a factory subclass gets bounded probes; one unbuildable provider does not hide others' readiness.

## TPR-400 — Episode lifecycle races and normalization

### TPR-12 — Races
- [ ] Read config and revision atomically in `EpisodePlannerService.build_plan`.
- [ ] Create generation runs under `BEGIN IMMEDIATE` with a config-revision recheck and a no-second-pending/running-run guard.
- [ ] Pass the guided wizard's loaded revision into `EpisodeConfigurationService.edit` and enforce it inside the update transaction.
- [ ] Hook-injected race tests for each window; two concurrent starts yield exactly one run; an edit after preflight makes start fail with a typed conflict.

### TPR-13 — No-op comparison normalization
- [ ] Define one canonical normalization (text strip, tuple host IDs, `None`/blank policy, integer seconds) at the service boundary.
- [ ] Route CLI, Quick, guided and legacy setup writes through it.
- [ ] Cross-surface table test: whitespace, `None`/`""` and list/tuple variants preserve plan identity; real changes still invalidate.

## TPR-500 — Configuration and security

### TPR-19.2 — Quick echoes a rejected research value
- [ ] Parse the Quick research override through the shared `UserConfig` normalizer (case and alias handling) and raise a generic error `from None`.
- [ ] Canary test across Quick CLI and TUI; mixed-case valid value accepted consistently with Settings.

### TPR-19.3 — Settings normalization order
- [ ] Route Settings default saves through `validate_candidate` (normalize then reference-check), matching `provider_tui.py`.
- [ ] Table test: identical input gives identical outcome and stored value through Settings, ProviderController and first-run.

### TPR-19.4 — Fragment redaction truncation
- [ ] Terminate `_URL_FRAGMENT` matches at URL delimiters (quotes, `<>`, `)`, `]`, `}`, `,`, whitespace).
- [ ] Tests on JSON, prose, Markdown links and multiple URLs per line: canary absent, context intact.

### TPR-19.5 — Sanitizer coverage gaps
- [ ] Redact userinfo for any `scheme://user:pass@host`.
- [ ] Extend sensitive keys (`code`, `sig`, `signature`, `x-amz-signature`, `x-goog-signature`, `id_token`, `refresh_token`) for query and fragment forms, including hybrid fragments.
- [ ] Decode `%23` / `%3D` inside the bounded decode loop before fragment/query matching.
- [ ] Canary matrix test for each case; benign URLs unchanged.

### TPR-19.6 — Lock re-entrancy
- [ ] Make `UserConfigStore._locked` truly re-entrant (depth counter, reuse the held descriptor) or a plain `Lock` with a non-nesting assertion.
- [ ] Test under a timeout: nested acquisition succeeds or fails fast, never hangs.

### TPR-19.7 — Minor validation and quality items
- [ ] Accept uppercase URL schemes and normalize them to lowercase.
- [ ] Extract one control-character helper in `UserConfig.validate_defaults`; behavior unchanged.
- [ ] Consolidate the `_redact_text` decode loops and document the pass order.
- [ ] Remove the redundant `os.fchmod` in `_write_temporary` or document why it stays.
- [ ] Existing config and diagnostics suites green after the refactors.

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

- [ ] Add a dated "Post-closeout review 2026-10-13" note to the second-cycle TODO listing each contradicted item with a pointer to this spec; checked state unchanged.
- [ ] Update `docs/GUIDED_WORKFLOW_USER_GUIDE.md` for the saturated-retry behavior, project editing policy and scoped host discard.
- [ ] Update `docs/ARCHITECTURE.md` for plan revision/CAS approval, run-creation guard, the dirty-form snapshot contract and the readiness fingerprint source.

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
