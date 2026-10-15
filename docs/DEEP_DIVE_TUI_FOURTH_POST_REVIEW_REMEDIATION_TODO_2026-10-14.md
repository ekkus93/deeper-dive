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

- [ ] Record the baseline head (`4ede40e`), its local check result (2,260 passed) and CI result (run 38674826121, `fresh-machine` failed).
- [ ] Every "Reproduced" item has a committed regression test that fails on the baseline; every "Source-verified" item has a deterministic reproducer or a justified N/A.

## FPR-100 — CI unblock (do first)

- [ ] Replace `tests/test_second_post_review_dirty_navigation.py` in `.github/workflows/ci.yml` `fresh-machine` with the three `..._part{1,2,3}.py` files.
- [ ] Add a check (script or test) that every `tests/*.py` path named in `.github/workflows/ci.yml` exists, so a rename cannot silently break `fresh-machine` again; run it from `scripts/check.sh`.
- [ ] Green exact-head CI (both jobs) recorded with run and job IDs.

## FPR-200 — Crashes and durable-state corruption

### FPR-01 — Stale AI choice after preset discard
- [ ] Real-input regression: durable Ollama `local` → choose OpenAI → Continue → Back → Discard → Continue → Save Provider; assert durable config bytes unchanged (fails on baseline).
- [ ] Discard restores the AI choice matching the durable provider, or Save derives the adapter from restored/durable state; document the chosen design.
- [ ] Save Provider refuses with a visible status when the AI choice and provider fields disagree on adapter type.
- [ ] `_capture_preset_baseline` never lets a preset become the clean baseline when a differing stored baseline exists; regression test for that path.

### FPR-02 — Legacy Episode Plan screen crashes
- [ ] Real-click regressions: Regenerate Plan and Regenerate Segment with a generation run present; provider failure; plan deleted between load and Save Segment → app alive, sanitized status, durable plan unchanged.
- [ ] `save`, `regenerate plan`, `regenerate segment` and `approve` catch `KeyError`, `ValueError`, `RuntimeError`, `OSError`, `sqlite3.Error` and the typed episode errors.
- [ ] Sweep every legacy `tui.py` screen action that calls a planner/config/run service; record each with its disposition.

### FPR-03 — Guided resume crash on free-text audience
- [ ] Real-input regression: episode created via service with audience "college students" → guided draft at that episode → fresh app → Resume → app alive (fails on baseline).
- [ ] Decide and document the policy for stored values the guided Select cannot represent (extra "Custom" option vs. BLANK + status); a no-op Save leaves the durable value unchanged.
- [ ] Audit every raw `Select.value =` in `guided_*.py` and `wizard_shell*.py`; route stored-data hydration through `_assign_select`; record the list.

### FPR-04 — Fail-closed discard crashes on non-blank Selects
- [ ] Parametrized test over every `_FORM_FIELDS` step with the baseline removed → Discard → no exception, no unsaved value retained, missing-baseline diagnostic asserted.
- [ ] Fail-closed discard reloads durable state where a loader exists; otherwise clears Inputs and resets `allow_blank=False` Selects to a valid default via the guarded helper.

### FPR-05 — Select transition after the target vanished
- [ ] Real-input regression for host select: edit A → pick B → delete B via service → Save-and-select → app alive, A saved, status explains B is gone.
- [ ] Deterministic tests for the plan-segment and speech-choice transition paths.
- [ ] `guided_host_wizard.py:269`, `guided_episode_wizard.py:294`, `guided_first_run.py:353` use the guarded helper.

## FPR-300 — Lifecycle integrity

### FPR-06 — Second active generation run
- [ ] SQLite regression: running run with `cancel_requested=1` → start refused, no new row (fails on baseline).
- [ ] `select_or_create` refuses while any `pending`/`running` run exists for the episode, inside `BEGIN IMMEDIATE`; start service and both UIs show "previous run is still stopping".
- [ ] Old run reaches a terminal state → start succeeds; concurrent-start thread test still yields one run.

### FPR-07 — Approval of an unreviewed plan
- [ ] Service regression: load P1, regenerate to P2 under the same config, approve with P1's ID → typed conflict, P2 still draft (fails on baseline).
- [ ] `approve_plan` takes the reviewed plan ID; legacy and guided callers pass it; legacy plan screen shows a sanitized conflict (pilot).
- [ ] Decide re-approval of an approved plan (no-op vs error); implement `status='draft'` in the CAS if error; docs match.

### FPR-14 — Stale segments under a newer config
- [ ] Hook regression: edit between plan load and snapshot in `regenerate_segment` and `edit_segment` → typed conflict, nothing persisted.
- [ ] Snapshot first, then load the plan; missing plan or digest mismatch fails.

### FPR-17 — Normalization gaps
- [ ] `normalized()` covers `source_overrides`, `model_overrides`, stripped `research_overrides` values; `focus=None` raises `ValueError`.
- [ ] `edit()` no-op path returns the revision it compared against; table test extended.

## FPR-400 — Sanitizer (FPR-08)

- [ ] Canary matrix test with every spec §10 row (fails on baseline for each leak row).
- [ ] Userinfo: empty username and passwords containing `@` or `/` (split on the last `@` before the host).
- [ ] Partial-decode and fragment-key passes apply to all tokenized URL schemes, including custom schemes.
- [ ] Unterminated quoted Authorization redacted to end of line/input, including cap-truncated input.
- [ ] Fragment values stop at `,` (TPR-19.4 spec); `)` behavior decided and tested.
- [ ] Bare keys without `=` (`#credentials`, `?code` alone) are not secrets; benign corpus test (MDN anchors, `?lang=en&code=python`, prose with commas) unchanged.
- [ ] Lower priority: `Ocp-Apim-Subscription-Key` header; multi-word `password:` values — fix or record N/A with reason.
- [ ] Performance test extended to the new shapes at the input cap; still linear.

## FPR-500 — Wizard dirty-form contract

### FPR-09 — False dirty after external config change
- [ ] Real-input regression: save speech → Continue → change speech provider on the Providers screen → return → Back → no prompt, new durable values shown (fails on baseline).
- [ ] App-initiated re-hydration re-baselines steps that were clean and preserves steps with unsaved edits; first-run and New Deep Dive Back use the same baseline timing.

### FPR-10 — Picker change under an open prompt
- [ ] Regression: Back prompt open → change host picker → Discard → executed transition is Back with Back's scope (fails on baseline). Same for the plan picker.
- [ ] Pickers are disabled or their changes reverted and ignored while a confirmation is pending.

### FPR-11 — Resume swallowed after discarding a dirty prior wizard
- [ ] Regression for `new` and `resume` × Save/Discard: the original destination runs exactly once.

### FPR-12 — Profile-scoped host Save
- [ ] Decide: scope Save to the profile, or label exactly what Save persists; test; user guide updated.

### FPR-13 — Swallowed or narrow error handling
- [ ] `_refresh_plan` shows a sanitized status when the planning service cannot be built (test via service-boundary fault).
- [ ] Legacy setup screen planning step handles `sqlite3.Error` (test with a locked/failing database).
- [ ] Host-order load failure on screen resume keeps the previous order (test via fault injection).

## FPR-600 — Readiness and config

### FPR-15 — Build failures and capability
- [ ] Readiness view shows a sanitized per-provider build-failure reason (test).
- [ ] Per-provider build isolation catches constructor `ValueError`s, not only `ProviderConfigurationError`.
- [ ] `_normalized_type` no longer echoes the user-supplied type.
- [ ] `supports_probe_timeouts` requires a compatible `build()` signature or explicit opt-in (test with a subclass that overrides `build()` without the keyword).
- [ ] `docs/ARCHITECTURE.md` probe-bound wording corrected (deadline start; `health()` + `models()` overrun).

### FPR-16 — Lock path aliasing
- [ ] Regression under a timeout: nested `_locked()` via `d/config.json` and `d/sub/../config.json` on one thread does not deadlock (fails on baseline).
- [ ] Re-entrancy key uses `path.resolve()` or `(st_dev, st_ino)`; descriptor closed even if `LOCK_UN` raises.
- [ ] Cross-thread exclusion test: thread A holds a nested lock, thread B waits until release.

## FPR-700 — Test quality (FPR-18)

- [ ] `guided_pilot.reach_hosts` and the restart test reach state through input, or each remaining direct call is documented in the helper docstring with the reason.
- [ ] TPR-04 approval race variant in which the plan survives, so only the revision CAS rejects.
- [ ] Edit-after-preflight test through `GenerationStartService.start()`.
- [ ] TPR-03 concurrent-writer cases use a real concurrent edit instead of patching `edit()`.
- [ ] Raising readiness subscriber: assert the log entry is sanitized.
- [ ] Fix weak assertions in `test_typed_host_edit_blocks_reselect_until_discarded` and `test_third_post_review_real_input_flow.py`; fix the restart test's misleading comment.
- [ ] Replace fixed `pilot.pause(0.3)` waits with condition waits where possible; document the button debounce where not.

## FPR-800 — Design follow-ups (FPR-19)

- [ ] `on_mount` single-dispatch (like the button/select handlers), or documented and tested idempotence; record per-wizard call counts before/after.
- [ ] Baseline bookkeeping: one API or documented invariants in `docs/ARCHITECTURE.md`.
- [ ] Status messages map widget IDs to field labels.
- [ ] Project step button reads "Save Project" in edit mode.
- [ ] Create Host idempotence scoped to the double-submit window.

## FPR-900 — Documentation and reconciliation (FPR-20)

- [ ] Third-cycle TODO: dated "Post-closeout review 2026-10-14" note listing each contradicted item with a pointer to this spec; status header and ledger rows corrected (TPR-16 enforced, TPR-17/18 complete, missing commits and test files); overstated claims annotated (TPR-04 `status='draft'`, TPR-600 real input, TPR-700). No checked state changed.
- [ ] `docs/ARCHITECTURE.md`: remove "TPR-17 … remains open"; "refuses a second active run" matches FPR-06; qualify "UI thread never waits on a writer".
- [ ] One-line old→new test path notes in `DEEP_DIVE_TUI_GUIDED_WORKFLOW_TODO_2026-10-08.md` and `DEEP_DIVE_SECOND_POST_REVIEW_CONSUMER_INVENTORY_2026-10-12.md`.
- [ ] `docs/GUIDED_WORKFLOW_USER_GUIDE.md` updated for FPR-03 policy, FPR-06 message, FPR-12 decision.

## FPR-910 — Independent review and final qualification

- [ ] Fresh read-only reviewer (no prior conclusions) traces every changed source path and sibling sweep; findings fixed or recorded.
- [ ] `uv lock --check`; ruff format and lint; strict mypy; full pytest count recorded.
- [ ] `uv build`; fresh-venv wheel install smoke.
- [ ] Green exact-head CI, both jobs, with run and job IDs.
- [ ] Evidence ledger below complete; every row's test fails with its fix reverted (Mutation column).

## Evidence ledger

| Item | Outcome | Commit(s) | Test file(s) | Mutation |
|---|---|---|---|---|
| FPR-01 | | | | |
| FPR-02 | | | | |
| FPR-03 | | | | |
| FPR-04 | | | | |
| FPR-05 | | | | |
| FPR-06 | | | | |
| FPR-07 | | | | |
| FPR-08 | | | | |
| FPR-09 | | | | |
| FPR-10 | | | | |
| FPR-11 | | | | |
| FPR-12 | | | | |
| FPR-13 | | | | |
| FPR-14 | | | | |
| FPR-15 | | | | |
| FPR-16 | | | | |
| FPR-17 | | | | |
| FPR-18 | | | | |
| FPR-19 | | | | |
| FPR-20 | | | | |
