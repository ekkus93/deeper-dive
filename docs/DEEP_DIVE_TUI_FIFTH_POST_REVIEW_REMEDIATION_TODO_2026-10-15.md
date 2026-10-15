# Deeper Dive TUI — Fifth Post-Review Remediation TODO

**Created:** 2026-10-15 (America/Los_Angeles)  
**Status:** Not started  
**Authority:** `docs/DEEP_DIVE_TUI_FIFTH_POST_REVIEW_REMEDIATION_SPEC_2026-10-15.md`  
**Reviewed baseline:** `96a5b54` (CI run 38694930846 green; local 2,432 passed on the `4384113` tree)  
**Predecessor historical checklist:** `docs/DEEP_DIVE_TUI_FOURTH_POST_REVIEW_REMEDIATION_TODO_2026-10-14.md`

This is the only completion checklist for the fifth post-review cycle. No item is prechecked. A checked item must identify:

- the production behavior that changed;
- a deterministic test that failed before the fix;
- the commit SHA;
- a green exact-head CI run.

If a reproducer disproves a finding, keep the task visible and record a justified N/A with exact evidence.

## Execution rules

- At every run start and after every `master` push, reload this TODO and the spec, inspect the exact head and its CI, and avoid duplicating landed work.
- One task per commit, with the task ID in the message and no `Co-Authored-By` trailers. Push only after `./scripts/check.sh` exits 0 with an `N passed` line.
- **CI is part of done.** `check.sh` does not run `fresh-machine`. A commit that renames, moves or deletes a test file updates `.github/workflows/ci.yml` in the same commit. Record the green run ID before ticking.
- **Test first**, at the highest practical boundary.
  - Wizard defects: real Textual input via `tests/guided_pilot.py`.
  - Storage defects: service- or DB-level tests.
  - Any test that seeds `context.state`, calls `action_*` or `on_screen_resume` directly, or assigns `widget.value` records why in a comment.
  - Where the spec names an acceptance step, the test performs it.
- **Sweep siblings:** every fix greps for the same pattern elsewhere and records the result (fixed, or out of scope with a reason) in the item's evidence line.
- **Stored-data compatibility:** a stricter validator or narrower control is checked against every shape that the CLI, legacy screens and earlier versions can store.
- **Review fixes** are tested, swept and mutation-checked like task fixes, and the ledger names their SHA.
- **Any `src/` change after 5PR-912 re-opens 5PR-912.**
- Do not change checked state in the fourth-cycle TODO; 5PR-12 adds annotations and ledger corrections only.

## 5PR-000 — Baseline

- [ ] Record the baseline head (`96a5b54`), a fresh full local check count on it, and CI run 38694930846.
- [ ] Every "Reproduced" item has a committed regression test that fails on the baseline. Every "Source-verified" item has a deterministic reproducer or a justified N/A. List any test rows that already pass on the baseline, rather than claiming every file failed.

## 5PR-100 — Regressions and stored-data loss

### 5PR-01 — Credential URL leak with terminators in the password
- [ ] Canary rows that fail on the baseline:
  - `https://user:pa#ssCANARY9x@host/x`
  - `https://user:pa?ssCANARY9x@host/x`
  - `postgres://user:pa'CANARY9x@db/x`
  - `https://user:CANARY9x"@host`
  - `<` and `>` variants
  - each of these embedded in JSON and in a Python repr
- [ ] `_userinfo_end` accepts `user:password@host` with authority terminators in the password when the authority has no `@`, and stays linear.
- [ ] The `host:port/path?email=a@b` benign case stays unredacted. The precedence rule is documented in the docstring and tested both ways.
- [ ] Each shape is checked through `redact()`, `sanitize_exception_message()` and the CLI error path. Record the worst-case timing at the 262,144-character cap.

### 5PR-02 — Unreachable stopping run blocks generation
- [ ] DB-level regression that fails on the baseline: legacy r1 (`running`, `cancel_requested`, worker gone) plus newer r2 (`pending`), then the documented command, then start succeeds with exactly one active run.
- [ ] Decide and document in `docs/GENERATION_RUN_SELECTION_POLICY.md` how cancel reaches the blocking run: oldest-blocking-first, or `--run <id>` with the refusal naming the run id.
- [ ] Decide and implement how a run whose worker is gone is finished (lease/heartbeat expiry or an explicit `--force` that marks it cancelled without executing a stage).
- [ ] The CLI cancel path never executes a stage for a run that another live process may own. Add a test.
- [ ] The refusal text, `cli.py` help and the user guide name the command that actually works. The concurrent-start thread test still yields one run.

### 5PR-03 — String-form model overrides lock the episode
- [ ] Service-level regression that fails on the baseline: an episode row with `{"episode_planning": "fake:fake-v1"}` can be loaded, snapshotted, planned with the fake provider and edited.
- [ ] `_normalized_model_overrides` accepts every shape `model_roles._assignment_from_override` accepts (preserved, or canonicalized with documentation) and still rejects unusable shapes.
- [ ] A stored invalid value surfaces a typed, field-naming error, and an edit that clears or replaces the overrides succeeds. Add a test.
- [ ] Sweep the other FPR-17 normalizers (`source_overrides`, `research_overrides`, `focus`) against the shapes existing writers store. Record the dispositions.

### 5PR-04 — Free-text depth and project audience rewritten
- [ ] Real-input pilot that fails on the baseline: store depth "graduate level" via the CLI or service, then Resume, change only the title, press Save. Stored depth is unchanged.
- [ ] Real-input pilot that fails on the baseline: project audience "policy makers", then Resume at the project step, change only the description, press Save. Stored audience is unchanged.
- [ ] Verify the duration case (stored 1830 seconds, then a no-op Save). Fix it, or record N/A with evidence.
- [ ] One shared helper for "show a stored value the preset Select cannot represent" replaces `_show_audience`'s single-use logic. Audience, depth and project audience use it.
- [ ] Re-audit every stored-data `Select.value =` and `Input.value =` in `guided_*.py` and `wizard_shell*.py` against the criterion "a no-op Save preserves the stored value". Record the list.

### 5PR-05 — First-run resume loses an unsaved preset pick
- [ ] Real-input pilot that fails on the baseline: choose OpenAI, Continue to `provider-config`, leave the wizard, Resume. The AI choice and the fields still show the unsaved pick, and durable bytes are unchanged.
- [ ] `on_screen_resume` treats every step that differs from its baseline as dirty, not just the current step. Document the chosen behavior: refuse the reload, or reload only the clean steps.
- [ ] The AI choice and its preset baseline are preserved or discarded together. Add a test: Discard on `provider-config` after Resume restores the durable values and the matching AI choice.

## 5PR-200 — Robustness

### 5PR-06 — Slash fallback garbles JSON and code
- [ ] Benign rows that fail on the baseline: `{"url":"http://localhost:8080/x","email":"a@b.com"}` and `fetch('http://api:8080/v1/x').catch(e=>log('a@b.com'))` round-trip unchanged.
- [ ] Bound the fallback token at `"`, `'`, `,` and `)`. Design it together with 5PR-01; all 5PR-01 and fourth-cycle matrix rows still pass.
- [ ] Update the docstring's list of known trade-offs.

### 5PR-07 — Remaining legacy crashes and mislabelled outcomes
- [ ] Mechanical sweep (AST walk or grep) of every legacy `action_*` that calls a service, composition or controller. Record the exact count and the list. Correct the fourth cycle's "20" (actual: 19 decorated).
- [ ] Fault-injection or real-click tests for the actions that crash on the baseline:
  - research save, analyze, search, ignore and research-all
  - transcript export (`OSError`) and regenerate turn
  - preflight Generate (`sqlite3.Error`, and `build` raising)
  - host save and relationship save (`sqlite3.Error`, `OSError`)
- [ ] Each of those actions is guarded with the shared error set and a sanitized status.
- [ ] `report_service_errors` (or its callers) distinguishes "service failed" from "saved, but the view could not refresh". Test: the service succeeds and the refresh raises, and the status says the change was saved.
- [ ] The legacy Episode Plan screen gets a Reload action or a resume reload that shows the stored plan without regenerating. Test: conflict, then Reload, then the newer plan is shown and the stored plan is unchanged.

### 5PR-08 — Pre-existing sanitizer gaps
- [ ] Fix the cap row so it actually cuts mid-secret, making it fail on a sanitizer that leaks.
- [ ] Canary and benign rows for:
  - one-word keys (`apikey=`, `accesstoken=`, `clientsecret=`, `passwd=`)
  - a PEM private-key body
  - `bytes` header reprs
  - unclosed quoted values
  - a credential URL cut before `@` by the cap
  - a percent-encoded non-HTTP URL
  - a custom-scheme fragment secret
- [ ] Fix each gap, or record it as accepted with a reason in the matrix file and the ledger.

### 5PR-09 — Cross-process lock aliasing
- [ ] Regression that fails on the baseline: two stores on aliased (symlinked) paths in separate processes or file descriptors exclude each other.
- [ ] `_open_advisory_lock` derives the lock file from the resolved path, keeping `O_NOFOLLOW` on the lock file.

### 5PR-10 — Residuals and latent defects
- [ ] `EpisodeSetupScreen`:
  - database reads in `_configuration`, `_host_ids`, `_planning_assignment`, `refresh_summary` and `action_quick_deep_dive` are guarded;
  - database errors are no longer attributed to the provider;
  - a test with a locked database keeps the app alive.
- [ ] A stale `host_order_notice` no longer reappears on a later step. Add a test.
- [ ] `load_plan` concurrent-delete `IndexError` becomes a single read or a typed conflict. Add a test.
- [ ] Correct the `edit_segment` docstring. Correct the FPR-07 caller claim in the fourth-cycle TODO annotation.
- [ ] The Discard restore fallback uses `_reset_select`. Add a test with an `allow_blank=False` Select.
- [ ] Create Host: `_last_created_host_id` is reset when the form changes, or the comment is corrected. Add a test.
- [ ] Picker change under a prompt with `_loaded_host_id is None`: the change is reverted, or there's a documented reason it can't happen.

## 5PR-300 — Tests and process

### 5PR-11 — Test quality
- [ ] FPR-03 test: Resume via real input and press Save after resume; assert the stored audience is unchanged.
- [ ] FPR-04 test: assert the visible status. Add a case showing a later Save does not write the adopted first option unasked.
- [ ] FPR-05 and FPR-11 tests: assert the visible status and that the transition runs exactly once. Use real input where reachable, otherwise add a justification comment.
- [ ] FPR-17 `test_noop_returns_the_record_it_compared_against` made discriminating: it fails with the fix reverted.
- [ ] FPR-18 residuals:
  - remaining `BUTTON_SETTLE_SECONDS` waits become condition waits, or the debounce is documented per use;
  - add the `prior_wizard_destination` justification comment;
  - `type_into` clears through key presses, or the reason is documented.
- [ ] Extend the CI path check to `file::node` ids listed in `.github/workflows/ci.yml`. It fails if a named test function is renamed.

### 5PR-12 — Process and documentation reconciliation
- [ ] `docs/ARCHITECTURE.md:230`: paused runs are exempt. Updated again for the 5PR-02 design.
- [ ] Fourth-cycle TODO annotations, dated and without unchecking:
  - line 63, pending/running/paused;
  - FPR-02, 20 → 19;
  - FPR-03 audit and the rewrite issue;
  - FPR-04 loader claim;
  - FPR-09 and 5PR-05;
  - FPR-000 overstated "each file failed";
  - FPR-07 caller claim.
- [ ] Fourth-cycle ledger and evidence corrections:
  - "review-fix commit" → `e55b78f` in rows FPR-06, 08 and 17;
  - `_split_userinfo` → `_userinfo_end`;
  - "worst 0.6 s" → 1.46 s;
  - note that the wheel smoke ran on `040fb74`, before `e55b78f`;
  - record head `96a5b54` run 38694930846.
- [ ] Add a "Post-closeout review 2026-10-15" note in the fourth-cycle TODO pointing to this cycle for FPR-02, 03, 04, 06, 08, 09, 17 and 910.
- [ ] The user guide and `GENERATION_RUN_SELECTION_POLICY.md` match 5PR-02's command and message.

## 5PR-900 — Review and qualification

### 5PR-911 — Independent review
- [ ] A fresh read-only reviewer with no prior conclusions traces every changed source path and sibling sweep. Every finding is fixed (with a test, a sweep and a mutation check) or recorded as accepted with a reason. Review-fix commits are named by SHA.

### 5PR-912 — Final qualification (after the last `src/` change)
- [ ] `uv lock --check`; ruff format and lint; strict mypy; full pytest count recorded at the exact head.
- [ ] `uv build`; fresh-venv wheel install smoke at the exact head, including one 5PR-01 redaction check and `deeper-dive episode cancel --help`.
- [ ] Green exact-head CI on both jobs, with run and job IDs.
- [ ] Evidence ledger below complete. Every row's test fails with its fix reverted (Mutation column), including review fixes.

## Evidence ledger

| Item | Outcome | Commit(s) | Test file(s) | Mutation |
|---|---|---|---|---|
| 5PR-01 | | | | |
| 5PR-02 | | | | |
| 5PR-03 | | | | |
| 5PR-04 | | | | |
| 5PR-05 | | | | |
| 5PR-06 | | | | |
| 5PR-07 | | | | |
| 5PR-08 | | | | |
| 5PR-09 | | | | |
| 5PR-10 | | | | |
| 5PR-11 | | | | |
| 5PR-12 | | | | |
