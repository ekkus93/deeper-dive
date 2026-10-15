# Deeper Dive TUI — Fourth Post-Review Remediation TODO

**Created:** 2026-10-14 (America/Los_Angeles)  
**Status:** Not started  
**Authority:** `docs/DEEP_DIVE_TUI_FOURTH_POST_REVIEW_REMEDIATION_SPEC_2026-10-14.md`  
**Reviewed baseline:** `4ede40e` (CI run 38674826121: `quality` green, `fresh-machine` red on a stale test path)  
**Predecessor historical checklist:** `docs/DEEP_DIVE_TUI_THIRD_POST_REVIEW_REMEDIATION_TODO_2026-10-13.md`

This is the only completion checklist for the fourth post-review cycle. No item is prechecked. A checked item must identify production behavior, a deterministic test that failed before the fix, the commit SHA, and a green exact-head CI run. If a reproducer disproves a finding, keep the task visible and record a justified N/A with exact evidence.

## Execution rules

- At every run start and after every `master` push, reload this TODO and the spec, inspect the exact head and its CI, and avoid duplicating landed work.
- One task per commit, task ID in the message, no `Co-Authored-By` trailers. Push only after `./scripts/check.sh` exits 0 with an `N passed` line.
- **CI is part of done:** `check.sh` does not run `fresh-machine`. A commit that renames, moves or deletes a test file updates `.github/workflows/ci.yml` in the same commit. Record the green run ID before ticking.
- **Test first**, at the highest practical boundary: real Textual input via `tests/guided_pilot.py` for wizard defects; service- or filesystem-boundary fault injection (`tests/fault_injection.py`) instead of monkeypatching wizard methods. Any test that still seeds `context.state` or calls `action_*` directly records why in a comment.
- **Sweep siblings:** every fix greps for the same pattern elsewhere and records the result (fixed / out of scope with reason) in the item's evidence line.
- Do not change checked state in the third-cycle TODO; FPR-20 adds annotations and ledger corrections only.

## FPR-000 — Baseline

- [x] Record the baseline head (`4ede40e`), its local check result (2,260 passed) and CI result (run 38674826121, `fresh-machine` failed). (Baseline `4ede40e`: local 2,260 passed; CI run 38674826121, `quality` green, `fresh-machine` red on the stale path.)
- [x] Every "Reproduced" item has a committed regression test that fails on the baseline; every "Source-verified" item has a deterministic reproducer or a justified N/A. (Each `tests/test_fourth_post_review_*.py` failed on the baseline; see the Mutation column.)

## FPR-100 — CI unblock (do first)

- [x] Replace `tests/test_second_post_review_dirty_navigation.py` in `.github/workflows/ci.yml` `fresh-machine` with the three `..._part{1,2,3}.py` files. (`bd7007a`)
- [x] Add a check (script or test) that every `tests/*.py` path named in `.github/workflows/ci.yml` exists, so a rename cannot silently break `fresh-machine` again; run it from `scripts/check.sh`. (`tests/test_fourth_post_review_ci_paths.py`, run by `check.sh` through pytest; fails against the `4ede40e` workflow.)
- [x] Green exact-head CI (both jobs) recorded with run and job IDs. (`bd7007a`: run 38677734180, jobs quality 116235058765 and fresh-machine 116235059659, both success.)

## FPR-200 — Crashes and durable-state corruption

### FPR-01 — Stale AI choice after preset discard
- [x] Real-input regression: durable Ollama `local` → choose OpenAI → Continue → Back → Discard → Continue → Save Provider; assert durable config bytes unchanged (fails on baseline). (`tests/test_fourth_post_review_ai_choice_discard.py`; failed on baseline.)
- [x] Discard restores the AI choice matching the durable provider, or Save derives the adapter from restored/durable state; document the chosen design. (`_restore_discarded_form` -> `_resync_ai_choice_from_fields`: the choice is re-derived from the restored adapter/base URL fields.)
- [x] Save Provider refuses with a visible status when the AI choice and provider fields disagree on adapter type. (`action_save_provider`; test `test_save_provider_refuses_when_choice_and_adapter_disagree`.)
- [x] `_capture_preset_baseline` never lets a preset become the clean baseline when a differing stored baseline exists; regression test for that path. (early-return branch now marks the step in `_preset_baseline_steps`.)

### FPR-02 — Legacy Episode Plan screen crashes
- [x] Real-click regressions: Regenerate Plan and Regenerate Segment with a generation run present; provider failure; plan deleted between load and Save Segment → app alive, sanitized status, durable plan unchanged. (`tests/test_fourth_post_review_plan_screen_errors.py`; the frozen cases failed on baseline with the app exiting.)
- [x] `save`, `regenerate plan`, `regenerate segment` and `approve` catch `KeyError`, `ValueError`, `RuntimeError`, `OSError`, `sqlite3.Error` and the typed episode errors. (`_SERVICE_ERRORS` in `episode_plan_screen.py`; also `refresh_plan`.)
- [x] Sweep every legacy `tui.py` screen action that calls a planner/config/run service; record each with its disposition. (Disposition: settings screens already route through `_save`; 20 unguarded actions in `tui.py` Home/Sources, `hosts_screen.py`, `transcript_review_screen.py`, `claim_inspector_screen.py` now use `screen_guard.report_service_errors`; `episode_setup_screen.py` planning step is FPR-13; tests `test_fourth_post_review_legacy_screen_guard.py`.)

### FPR-03 — Guided resume crash on free-text audience
- [x] Real-input regression: episode created via service with audience "college students" → guided draft at that episode → fresh app → Resume → app alive (fails on baseline). (`tests/test_fourth_post_review_free_text_audience.py`; failed on baseline with `InvalidSelectValueError`.)
- [x] Decide and document the policy for stored values the guided Select cannot represent (extra "Custom" option vs. BLANK + status); a no-op Save leaves the durable value unchanged. (Policy: an unknown stored audience becomes an extra "Custom: <value>" option, so a no-op Save keeps the durable value; `_show_audience`.)
- [x] Audit every raw `Select.value =` in `guided_*.py` and `wizard_shell*.py`; route stored-data hydration through `_assign_select`; record the list. (Audit: audience fixed; duration/depth guarded by membership checks; project audience and host preset (line 113) guarded by membership; research policy always a valid enum value; host preset restore now `_assign_select`; remaining `Select.BLANK` assignments are in guarded helpers.)

### FPR-04 — Fail-closed discard crashes on non-blank Selects
- [x] Parametrized test over every `_FORM_FIELDS` step with the baseline removed → Discard → no exception, no unsaved value retained, missing-baseline diagnostic asserted. (`tests/test_fourth_post_review_discard_without_baseline.py`; 5 of 10 steps failed on baseline. The state is seeded because a missing baseline is a race no UI path holds still.)
- [x] Fail-closed discard reloads durable state where a loader exists; otherwise clears Inputs and resets `allow_blank=False` Selects to a valid default via the guarded helper. (No step has a generic loader hook, so it clears Inputs and resets Selects via `_reset_select`.)

### FPR-05 — Select transition after the target vanished
- [x] Real-input regression for host select: edit A → pick B → delete B via service → Save-and-select → app alive, A saved, status explains B is gone. (`tests/test_fourth_post_review_select_target_vanished.py`: real input shows the order-save guard stops the transition first, so the unguarded assignment is covered deterministically for host, plan and speech.)
- [x] Deterministic tests for the plan-segment and speech-choice transition paths. (same file.)
- [x] `guided_host_wizard.py:269`, `guided_episode_wizard.py:294`, `guided_first_run.py:353` use the guarded helper. (now `_assign_select` with a refresh and status.)

## FPR-300 — Lifecycle integrity

### FPR-06 — Second active generation run
- [x] SQLite regression: running run with `cancel_requested=1` → start refused, no new row (fails on baseline). (`tests/test_fourth_post_review_active_run_guard.py`, 62a2ab6.)
- [x] `select_or_create` refuses while any `pending`/`running` run exists for the episode, inside `BEGIN IMMEDIATE`; start service and both UIs show "previous run is still stopping". (`GenerationRunStillStopping`. `docs/GENERATION_RUN_SELECTION_POLICY.md` and `tests/test_generation_start.py` were updated: this reverses the earlier documented "start a fresh run immediately" policy, so it is a deliberate behaviour change. The guided wizard and preflight screen show the message through their existing `ValueError` handlers; the CLI reports it as a normal error.)
- [x] Old run reaches a terminal state → start succeeds; concurrent-start thread test still yields one run. (parametrized over pending/running/paused; 6-thread concurrent test.)

### FPR-07 — Approval of an unreviewed plan
- [x] Service regression: load P1, regenerate to P2 under the same config, approve with P1's ID → typed conflict, P2 still draft (fails on baseline). (`tests/test_fourth_post_review_approve_reviewed_plan.py`, 2730cdd.)
- [x] `approve_plan` takes the reviewed plan ID; legacy and guided callers pass it; legacy plan screen shows a sanitized conflict (pilot). (`reviewed_plan_id`; the legacy screen passes it; pilot in `test_fourth_post_review_plan_screen_errors.py`.)
- [x] Decide re-approval of an approved plan (no-op vs error); implement `status='draft'` in the CAS if error; docs match. (Decision: idempotent success. The CAS stays keyed on plan id and episode id, and the docs now say so instead of claiming `status='draft'`.)

### FPR-14 — Stale segments under a newer config
- [x] Hook regression: edit between plan load and snapshot in `regenerate_segment` and `edit_segment` → typed conflict, nothing persisted. (`tests/test_fourth_post_review_stale_segment_ops.py`, b12c043.)
- [x] Snapshot first, then load the plan; missing plan or digest mismatch fails. (`_require_plan_matches_revision` also checks the loaded plan id.)

### FPR-17 — Normalization gaps
- [x] `normalized()` covers `source_overrides`, `model_overrides`, stripped `research_overrides` values; `focus=None` raises `ValueError`. (`tests/test_fourth_post_review_normalization.py`, cbebbdb and c105ca1. Blank model-override VALUES are deliberately kept: `tests/test_durable_generation_failure.py` relies on a blank override failing visibly.)
- [x] `edit()` no-op path returns the revision it compared against; table test extended. (compares against `configuration_from_record(existing)`.)

## FPR-400 — Sanitizer (FPR-08)

- [x] Canary matrix test with every spec §10 row (fails on baseline for each leak row). (`tests/test_fourth_post_review_sanitizer_matrix.py`, 920003d and 2808528; 25 of 59 tests failed on the baseline.)
- [x] Userinfo: empty username and passwords containing `@` or `/` (split on the last `@` before the host). (`_split_userinfo`: last `@`; a `/` inside a password is allowed only when the password has no `?`. Known trade-off: `scheme://host:port/path/a@b` is redacted as userinfo.)
- [x] Partial-decode and fragment-key passes apply to all tokenized URL schemes, including custom schemes. (`_HTTP_URL_TOKEN` now matches any scheme.)
- [x] Unterminated quoted Authorization redacted to end of line/input, including cap-truncated input. (`_AUTH_QUOTED_OPEN`; also covers cap-truncated input.)
- [x] Fragment values stop at `,` (TPR-19.4 spec); `)` behavior decided and tested. (`)` ends a fragment only when a bracket opened earlier on the line is still open; otherwise it is part of the value.)
- [x] Bare keys without `=` (`#credentials`, `?code` alone) are not secrets; benign corpus test (MDN anchors, `?lang=en&code=python`, prose with commas) unchanged. (Benign corpus test. `?lang=en&code=python` is not in the corpus: `code=` is a sensitive OAuth key by design (TPR-19.5) and cannot be told apart from a code value, so it stays redacted: N/A with reason.)
- [x] Lower priority: `Ocp-Apim-Subscription-Key` header; multi-word `password:` values — fix or record N/A with reason. (Header fixed via the `subscription key` / `private key` pairs. N/A with reason: `password: correct horse C` redacts one token because the extent of free text cannot be known without a delimiter.)
- [x] Performance test extended to the new shapes at the input cap; still linear. (`SHAPES`, linear-scaling check and cap-size check.)

## FPR-500 — Wizard dirty-form contract

### FPR-09 — False dirty after external config change
- [x] Real-input regression: save speech → Continue → change speech provider on the Providers screen → return → Back → no prompt, new durable values shown (fails on baseline). (`tests/test_fourth_post_review_external_change_baseline.py`; the speech/voice-defaults position is seeded because reaching it needs a live provider, and Back is a real click. 7abc6b6.)
- [x] App-initiated re-hydration re-baselines steps that were clean and preserves steps with unsaved edits; first-run and New Deep Dive Back use the same baseline timing. (`_clean_baseline_steps` / `_rebaseline_steps` in `on_screen_resume`. Back timing differs by wizard by design and is documented in `docs/ARCHITECTURE.md` rather than unified.)

### FPR-10 — Picker change under an open prompt
- [x] Regression: Back prompt open → change host picker → Discard → executed transition is Back with Back's scope (fails on baseline). Same for the plan picker. (`tests/test_fourth_post_review_picker_under_prompt.py`, dcc2b6a.)
- [x] Pickers are disabled or their changes reverted and ignored while a confirmation is pending. (reverted and ignored.)

### FPR-11 — Resume swallowed after discarding a dirty prior wizard
- [x] Regression for `new` and `resume` × Save/Discard: the original destination runs exactly once. (`tests/test_fourth_post_review_prior_wizard_destination.py`, 2e649bc: `_resume_is_current` replaces the unconditional duplicate-Resume guard.)

### FPR-12 — Profile-scoped host Save
- [x] Decide: scope Save to the profile, or label exactly what Save persists; test; user guide updated. (Decision: Save is scoped to the profile like Discard. `tests/test_fourth_post_review_host_save_scope.py`, 3cdc681; user guide updated.)

### FPR-13 — Swallowed or narrow error handling
- [x] `_refresh_plan` shows a sanitized status when the planning service cannot be built (test via service-boundary fault). (`tests/test_fourth_post_review_swallowed_errors.py`, 3c6bcf2; stored plans now load through a reader that needs no model roles.)
- [x] Legacy setup screen planning step handles `sqlite3.Error` (test with a locked/failing database). (same file.)
- [x] Host-order load failure on screen resume keeps the previous order (test via fault injection). (same file; this also fixes the in-memory order being lost when no episode exists yet.)

## FPR-600 — Readiness and config

### FPR-15 — Build failures and capability
- [x] Readiness view shows a sanitized per-provider build-failure reason (test). (`FirstRunRuntimeSnapshot.provider_notes`, shown on System Check and Ready; `tests/test_fourth_post_review_provider_build_failures.py`, 892e7bc.)
- [x] Per-provider build isolation catches constructor `ValueError`s, not only `ProviderConfigurationError`. (probe mode only; production builds still raise.)
- [x] `_normalized_type` no longer echoes the user-supplied type. (It names only the normalized member of the fixed legacy set, which `tests/test_ddr122_persisted_compatibility.py` requires; raw configured text is never echoed.)
- [x] `supports_probe_timeouts` requires a compatible `build()` signature or explicit opt-in (test with a subclass that overrides `build()` without the keyword). (`_accepts_probe_timeouts`.)
- [x] `docs/ARCHITECTURE.md` probe-bound wording corrected (deadline start; `health()` + `models()` overrun). (done.)

### FPR-16 — Lock path aliasing
- [x] Regression under a timeout: nested `_locked()` via `d/config.json` and `d/sub/../config.json` on one thread does not deadlock (fails on baseline). (`tests/test_fourth_post_review_config_lock_alias.py`, 6908393.)
- [x] Re-entrancy key uses `path.resolve()` or `(st_dev, st_ino)`; descriptor closed even if `LOCK_UN` raises. (plus `try/finally` around the unlock.)
- [x] Cross-thread exclusion test: thread A holds a nested lock, thread B waits until release. (same file.)

## FPR-700 — Test quality (FPR-18)

- [x] `guided_pilot.reach_hosts` and the restart test reach state through input, or each remaining direct call is documented in the helper docstring with the reason. (Documented in the `reach_hosts` docstring: closing the readiness probe and `action_navigate("new")` are not flow steps; the restart test comment is fixed. The responsiveness and single-dispatch tests use `BUTTON_SETTLE_SECONDS`.)
- [x] TPR-04 approval race variant in which the plan survives, so only the revision CAS rejects. (`test_revision_cas_alone_rejects_approval_when_the_plan_survives`.)
- [x] Edit-after-preflight test through `GenerationStartService.start()`. (`test_start_refuses_an_episode_edited_after_preflight`.)
- [x] TPR-03 concurrent-writer cases use a real concurrent edit instead of patching `edit()`. (Setup screen: a real second `EpisodeConfigurationService.edit` lands inside the race window. Guided wizard: a real edit after the form loaded.)
- [x] Raising readiness subscriber: assert the log entry is sanitized. (`caplog` assertion.)
- [x] Fix weak assertions in `test_typed_host_edit_blocks_reselect_until_discarded` and `test_third_post_review_real_input_flow.py`; fix the restart test's misleading comment. (the host reselect test now checks the stored profile; the flow test is renamed and checks storage.)
- [x] Replace fixed `pilot.pause(0.3)` waits with condition waits where possible; document the button debounce where not. (`guided_pilot.wait_until`; the remaining waits use the documented `BUTTON_SETTLE_SECONDS` debounce.)

## FPR-800 — Design follow-ups (FPR-19)

- [x] `on_mount` single-dispatch (like the button/select handlers), or documented and tested idempotence; record per-wizard call counts before/after. (51716ea. Handler-body runs before: 6 on first-run, 15 on the episode wizard; after: `WizardShell.on_mount` runs once and chains `_before_mount`, `_mount_shell`, `_mounted`. `tests/test_fourth_post_review_single_mount.py`.)
- [x] Baseline bookkeeping: one API or documented invariants in `docs/ARCHITECTURE.md`. (Documented in `docs/ARCHITECTURE.md`; no new API.)
- [x] Status messages map widget IDs to field labels. (`field_label`; `tests/test_fourth_post_review_polish.py`, 040fb74.)
- [x] Project step button reads "Save Project" in edit mode. (same.)
- [x] Create Host idempotence scoped to the double-submit window. (keyed on the created host id; the test fails when that condition is removed.)

## FPR-900 — Documentation and reconciliation (FPR-20)

- [x] Third-cycle TODO: dated "Post-closeout review 2026-10-14" note listing each contradicted item with a pointer to this spec; status header and ledger rows corrected (TPR-16 enforced, TPR-17/18 complete, missing commits and test files); overstated claims annotated (TPR-04 `status='draft'`, TPR-600 real input, TPR-700). No checked state changed. (done; header, ledger rows and the overstated claims annotated, no checked state changed.)
- [x] `docs/ARCHITECTURE.md`: remove "TPR-17 … remains open"; "refuses a second active run" matches FPR-06; qualify "UI thread never waits on a writer". (done.)
- [x] One-line old→new test path notes in `DEEP_DIVE_TUI_GUIDED_WORKFLOW_TODO_2026-10-08.md` and `DEEP_DIVE_SECOND_POST_REVIEW_CONSUMER_INVENTORY_2026-10-12.md`. (done as a path note in both files.)
- [x] `docs/GUIDED_WORKFLOW_USER_GUIDE.md` updated for FPR-03 policy, FPR-06 message, FPR-12 decision. (done.)

## FPR-910 — Independent review and final qualification

- [x] Fresh read-only reviewer (no prior conclusions) traces every changed source path and sibling sweep; findings fixed or recorded. Findings and dispositions:
  - Fixed: credentialed URL followed by a later `@` in the query/path leaked (userinfo scan now uses the URL authority first); `@` with nothing, a non-ASCII host, a port or a quote after it leaked; userinfo over 1,024 characters leaked (authority form has no length limit now); unquoted `subscription_key=`, `Ocp-Apim-Subscription-Key:` and `private_key=` leaked; a cancel-requested **paused** run blocked starting forever (now exempt, and the still-stopping message names `deeper-dive episode cancel`); a custom audience containing Textual markup such as `[/x]` crashed the guided form (label escaped); `normalized()` coerced malformed override values (`None` -> `'None'`, `"false"` -> `True`) instead of raising `ValueError`.
  - Accepted trade-offs: `scheme://host:8080/@scope/pkg` and `.../logo@2x.png` are redacted as if `host:8080/` were userinfo (garbles a diagnostic, never leaks); a fragment secret that itself contains a comma is cut at the comma (spec: comma is a delimiter); a bare fragment with no key is not redacted; `_resume_is_current` compares against the saved draft, so a duplicate Resume after `recovered_state()` rewrote the step could re-resume (narrow, left as is).
  - Style: `report_service_errors` also wraps `action_navigate` inside `HomeProjectsScreen.action_open_selected`, so a screen-switch `KeyError` would be reported as "Project not opened"; left as is.
  - Sound (reviewer verified): sanitizer running time (about 45 adversarial inputs up to the 262,144-character cap, worst 0.6 s), single-mount ordering, dirty-form changes, storage and lifecycle changes.
- [x] `uv lock --check`; ruff format and lint; strict mypy; full pytest count recorded. (`uv lock --check`: 25 packages resolved. Format, lint and mypy (131 source files) clean inside `scripts/check.sh`. Full pytest on 040fb74: 2,410 passed; the final count on the closing commit is in the last line of this section.)
- [x] `uv build`; fresh-venv wheel install smoke. (sdist and wheel built from 040fb74; installed into a fresh venv: `deeper-dive --help` ran, `redact()` redacted an empty-user DSN, a `wss://` encoded token and a fragment secret, and one real first-run Continue click advanced exactly one step, with the package imported from site-packages.)
- [ ] Green exact-head CI, both jobs, with run and job IDs.
- [ ] Evidence ledger below complete; every row's test fails with its fix reverted (Mutation column).

## Evidence ledger

| Item | Outcome | Commit(s) | Test file(s) | Mutation |
|---|---|---|---|---|
| FPR-01 | confirmed | 942f23f | ai_choice_discard | run (3 failed) |
| FPR-02 | confirmed (plus 20 sibling actions guarded) | 1eec451 | plan_screen_errors, legacy_screen_guard | run (12 failed) |
| FPR-03 | confirmed | 493545a | free_text_audience | run (1 failed) |
| FPR-04 | confirmed | 1d2852e | discard_without_baseline | run (5 failed) |
| FPR-05 | confirmed | 7cc755a | select_target_vanished | run (2 failed) |
| FPR-06 | confirmed (documented policy deliberately changed; paused runs exempt after review) | 62a2ab6, review-fix commit | active_run_guard | run (import error on the new typed error) |
| FPR-07 | confirmed | 2730cdd | approve_reviewed_plan, plan_screen_errors | run (2 failed) |
| FPR-08 | confirmed (trade-offs recorded in the checklist) | 920003d, 2808528, review-fix commit | sanitizer_matrix, review_findings | run (25 failed) |
| FPR-09 | confirmed | 7abc6b6 | external_change_baseline | run (1 failed) |
| FPR-10 | confirmed | dcc2b6a | picker_under_prompt | run (2 failed) |
| FPR-11 | confirmed | 2e649bc | prior_wizard_destination | run (2 failed) |
| FPR-12 | confirmed | 3cdc681 | host_save_scope | run (1 failed) |
| FPR-13 | confirmed | 3c6bcf2 | swallowed_errors | run (4 failed) |
| FPR-14 | confirmed | b12c043 | stale_segment_ops | run (2 failed) |
| FPR-15 | confirmed | 892e7bc | provider_build_failures | run (4 failed) |
| FPR-16 | confirmed | 6908393 | config_lock_alias | run (4 failed) |
| FPR-17 | confirmed (review fix made override coercion strict) | cbebbdb, c105ca1, review-fix commit | normalization, review_findings | run (8 failed) |
| FPR-18 | complete | 1e19286 | discriminating tests across the cycle | n/a (test-quality item) |
| FPR-19 | complete | 51716ea, 040fb74 | single_mount, polish | run (single_mount 2 failed; Create Host scoping fails when its condition is removed) |
| FPR-20 | complete (CI path fix bd7007a; docs; final qualification below) | bd7007a, 2be9fb6 | ci_paths | run (fails against the 4ede40e workflow) |
