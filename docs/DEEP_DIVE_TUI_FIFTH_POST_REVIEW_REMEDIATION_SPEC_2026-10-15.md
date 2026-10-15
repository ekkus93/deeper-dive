# Deeper Dive TUI — Fifth Post-Review Remediation Specification

**Created:** 2026-10-15 (America/Los_Angeles)  
**Status:** Not started  
**Reviewed `master` baseline:** `96a5b54` (fourth cycle closed; line references below are valid against this commit)  
**Companion authoritative implementation checklist:** `docs/DEEP_DIVE_TUI_FIFTH_POST_REVIEW_REMEDIATION_TODO_2026-10-15.md`  
**Predecessor (historical, do not rewrite checked state):** `docs/DEEP_DIVE_TUI_FOURTH_POST_REVIEW_REMEDIATION_TODO_2026-10-14.md` and its spec  
**CI at baseline:** run 38694930846 on `96a5b54` green (both jobs). Run 38692430344 on `4384113` green (quality 116281198665, fresh-machine 116281198853). Full local check on the `4384113` tree: 2,432 passed.

## 1. Executive summary

Three independent reviewers carried out a read-only review of the completed fourth post-review cycle (all 76 boxes ticked). They traced production code without the implementer's conclusions and wrote throwaway reproducers. Most fourth-cycle fixes are real: reverting each fix makes its test fail for FPR-01, 05, 07, 09, 10, 11, 12, 14 and 16. Plan approval and run selection are atomic. The single-mount refactor leaves widget, baseline and status state identical before and after on four flows. Sanitizer running time is linear up to the 262,144-character cap.

The review nevertheless found three regressions introduced by the late review-fix commit `e55b78f` (after the cycle had been qualified), two silent rewrites of stored data, and several ticked items whose evidence overstates what was done.

| ID | Priority | Status | Topic | Main production surface |
| --- | --- | --- | --- | --- |
| 5PR-01 | High | Reproduced (regression from `e55b78f`) | Credential URL whose password contains `#`, `?`, a quote or `<>` and no `/` is no longer redacted | `diagnostics.py` |
| 5PR-02 | High | Reproduced (DB level; regression from FPR-06) | A cancel-requested run that `episode cancel` cannot reach blocks generation forever; CLI cancel runs a stage while the old worker may still be running | `storage/run_repositories.py`, `cli.py`, `pipeline.py` |
| 5PR-03 | High | Reproduced (regression from `e55b78f`) | String-form model overrides (`"provider:model"`) accepted by `model_roles` are rejected by strict normalization, so the episode can't be planned or edited | `episode_config.py` |
| 5PR-04 | High | Reproduced | Free-text technical depth and project audience are silently rewritten to a preset on an unrelated Save | `guided_episode_form.py`, `guided_new_deep_dive.py` |
| 5PR-05 | Medium | Reproduced | First-run resume discards an unsaved AI-preset pick on a non-current step; the provider step then shows a false dirty state and Discard restores stale values | `guided_first_run.py` |
| 5PR-06 | Medium | Reproduced | Slash-in-password fallback garbles benign JSON and code (no leak) | `diagnostics.py` |
| 5PR-07 | Medium | Source-verified | FPR-02 sweep incomplete: legacy actions that still crash; decorator reports failure after a successful save; legacy plan screen has no reload after a conflict | `research_screen.py`, `transcript_review_screen.py`, `preflight_screen.py`, `hosts_screen.py`, `tui.py`, `screen_guard.py`, `episode_plan_screen.py` |
| 5PR-08 | Low | Reproduced | Sanitizer gaps that predate this cycle, and a vacuous cap test row | `diagnostics.py`, `tests/test_fourth_post_review_sanitizer_matrix.py` |
| 5PR-09 | Low | Source-verified | Config advisory-lock file is derived from the unresolved path, so two processes using different spellings of a symlinked path lock different files | `user_config.py` |
| 5PR-10 | Low | Source-verified | Residuals of FPR-07, 13, 14 and latent defects in Discard restore and Create Host | `episode_setup_screen.py`, `episode_planner.py`, `wizard_shell.py`, `guided_host_wizard.py` |
| 5PR-11 | Medium (quality) | — | Fourth-cycle tests that do not check what their item claims | `tests/` |
| 5PR-12 | Process | — | Reconcile the fourth-cycle TODO and docs; re-qualify at the exact head, including after any review-fix commit | fourth-cycle TODO, `docs/ARCHITECTURE.md`, `.github/workflows/ci.yml` |

"Reproduced" means a reviewer's throwaway script demonstrated the failure. Those scripts were not committed and must be rewritten as permanent regression tests. "Source-verified" means the defect follows from reading the code; the first task for each is a deterministic reproducer that fails on the baseline. If a reproducer disproves a finding, record the evidence and a narrowly justified N/A rather than deleting the task.

## 2. Governing execution contract

Everything in the fourth-cycle contract (spec §2) still applies: work on current `master`, one task per commit with the task ID, no `Co-Authored-By` trailers, push only after `./scripts/check.sh` exits 0 with an `N passed` line, exact-head CI is part of done, test first at the highest practical boundary, sweep sibling call sites, preserve production boundaries, artificial canaries and fake providers only. In addition:

- **Qualification is invalidated by any later production change.** The fourth cycle's wheel build and smoke ran on `040fb74`, and `e55b78f` then changed production code without repeating them. Two of the three regressions in this cycle came from that commit. Any commit that touches `src/` after the final-qualification step re-opens it.
- **Review fixes get the same treatment as task fixes:** a failing test first, a sibling sweep, and a mutation check (revert the fix, the test fails). Review-fix rows in the ledger name the exact commit SHA.
- **Compatibility with stored data.** A stricter validator or a narrower UI control must be checked against every shape that existing writers (CLI, legacy screens, earlier versions, imports) can have stored. The policy is: accept and preserve what other writers can store; reject only what nothing can produce, and then say so in a typed, visible error that offers a repair path.
- **"Real input" means real input.** A test that seeds `context.state`, calls `action_*` or `on_screen_resume` directly, or assigns `widget.value` instead of typing must say why in a comment. Where the spec names an acceptance step (e.g. "a no-op Save"), the test performs it.

## 3. 5PR-01 — Credential URL leak (regression from `e55b78f`)

### Defect
`_userinfo_end` (`diagnostics.py:78-111`) first matches `_AUTHORITY` (which ends at the first `/`, `?`, `#`, whitespace or quote) and looks for `@` inside it. When the password contains one of those terminators, the authority ends before the `@`, so the first branch finds nothing. The fallback branch then requires a `/` after the colon, which these URLs don't have, so it returns `None` and the URL passes through unredacted.

Reproduced leaks (the code before `e55b78f` redacted all of these):

- `https://user:pa#ssCANARY9x@host/x`
- `https://user:pa?ssCANARY9x@host/x`
- `postgres://user:pa'CANARY9x@db/x`
- `https://user:CANARY9x"@host`
- the same shapes with `<` or `>` in the password

### Required behavior
1. When the authority has no `@`, also accept a userinfo of the form `user:password@host` where the password contains authority terminators. The `:` must come before the `@`, there is no whitespace in between, and the character after the `@` is a host character (`_HOST_CHAR`). Choose the scan bound deliberately (whitespace or the existing window) and keep it linear.
2. Do not reintroduce the `host:port/path?email=a@b` false positive that the `?` guard exists for. Decide the precedence between "contains `?`" and "no `/` before the `@`", document it in the docstring, and test both directions.
3. Add every reproduced shape above to the sanitizer matrix as a canary row, along with the variant where the same URL sits inside JSON and inside a Python repr.

### Acceptance
Each shape above is redacted in `redact()`, `sanitize_exception_message()` and the CLI error path. The existing benign rows still pass unchanged. Timing stays linear at the cap (record the worst case).

## 4. 5PR-02 — Unreachable stopping run blocks generation forever

### Defect
`GenerationRunRepository.create` (`storage/run_repositories.py:94-98`) refuses to start while any pending or running run has `cancel_requested`. Its message tells the user to run `deeper-dive episode cancel`. That command acts only on `latest_for_episode` (`cli.py:380-390`).

Reproduced with a database written before FPR-06: r1 is `running` with `cancel_requested=1` and its worker is gone, and a newer r2 is `pending`. `episode cancel` cancels r2. r1 is never reached, and no TUI or CLI path can reach it, so the episode can never generate again.

Secondary problem: `episode cancel` calls `request_cancel` and then `composition.run_generation(...)` in-process (`cli.py:388-390`). That drives the run to a stage boundary from the CLI process while the original worker may still be running the same stage, which is the concurrent execution FPR-06 set out to prevent.

### Required behavior
1. `deeper-dive episode cancel` (and its TUI equivalent, if any) must be able to reach the run that blocks starting. Choose one design and document it in `docs/GENERATION_RUN_SELECTION_POLICY.md`:
   - (a) cancel targets the oldest blocking cancel-requested active run first, or
   - (b) a `--run <id>` option, with the refusal message naming the blocking run id and the exact command.
2. Define how a run whose worker is gone gets finished. Options include a worker lease or heartbeat with expiry, or an explicit `episode cancel --force` that marks the run `cancelled` without executing a stage. The default path must never execute a stage for a run that another live process may be executing.
3. The refusal text and the user guide must match the command that actually works.

### Acceptance
- DB-level regression: legacy r1 (running, cancel-requested) plus newer r2 (pending), then the documented command, then start succeeds with exactly one active run. This fails on the baseline.
- A test proves the CLI cancel path does not run a stage for a run that is marked as owned by a live worker (however liveness is modelled).
- The concurrent-start thread test still yields one run.

## 5. 5PR-03 — String-form model overrides lock the episode (regression from `e55b78f`)

### Defect
`model_roles._assignment_from_override` (`model_roles.py:159-164`) accepts a string override such as `{"episode_planning": "fake:fake-v1"}`. `_normalized_model_overrides` (`episode_config.py:41-55`), made strict in `e55b78f`, rejects anything that is not a mapping of strings. An episode stored with a string-form override therefore raises `ValueError` in `snapshot()`, in `build_plan`, and in every `edit()`, including an edit that would clear the override. The episode cannot be planned or repaired from the CLI, the legacy screen or the guided wizard.

### Required behavior
1. Normalization accepts every shape that `model_roles` accepts. A string `provider:model` or `provider/model` is either preserved as-is, or canonicalized to `{"provider", "model"}` with the conversion documented. It still rejects shapes nothing can use (non-string keys, `None`, booleans, nested non-string values).
2. Loading a stored row must never make the episode uneditable. If a stored value is genuinely invalid, the load surfaces a typed error naming the field, and an edit that replaces or clears the overrides succeeds.
3. Sweep the other strict normalizers added in FPR-17 (`source_overrides`, `research_overrides`, `focus=None`) for shapes that existing writers store. Record each one with its disposition.

### Acceptance
- Service-level regression: an episode row with a string-form override can be loaded, snapshotted, planned (with a fake provider) and edited.
- An edit that clears the override succeeds.
- Both fail on the baseline.

## 6. 5PR-04 — Free-text depth and project audience are silently rewritten

### Defect
FPR-03 fixed the guided episode audience by adding a "Custom: …" option. Its siblings were not fixed:

- **Technical depth** (`guided_episode_form.py:108-109`) is assigned only if it is one of `accessible`/`balanced`/`deep`. Otherwise the Select keeps its default `balanced`. The CLI `--depth` option and the legacy Episode Setup screen (`episode_setup_screen.py:50`, free-text Input) accept any text. Reproduced: store "graduate level", resume, edit only the title, Save, and depth becomes `balanced`.
- **Project audience** (`guided_new_deep_dive.py:75-76`) follows the same pattern for any audience outside `general`/`technical`/`expert`, and Save rewrites it.
- **To verify:** duration (`guided_episode_form.py:110-117`). A stored value that is not a whole number of minutes (the legacy screen takes seconds, e.g. 1830) is shown as a rounded custom value, and Save may write the rounded value back.

### Required behavior
1. Apply the FPR-03 policy to every guided control that hydrates from stored data that another writer can set freely: preserve the stored value through a no-op Save, and show it honestly. Use a shared helper rather than a third copy of `_show_audience`.
2. Duration: either preserve the exact stored seconds until the user changes the duration, or document and test why rounding is acceptable.
3. Grep every `Select.value =` and every `Input.value =` that hydrates from stored data in `guided_*.py` and `wizard_shell*.py`. Record each one with its disposition. The FPR-03 audit listed depth and project audience as "guarded by membership checks", which avoids the crash but not the rewrite. The audit criterion is now "a no-op Save preserves the stored value".

### Acceptance
Real-input pilots, each failing on the baseline:
- Free-text depth: resume, change only the title, press Save. Stored depth is unchanged.
- Free-text project audience: resume at the project step, change only the description, press Save. Stored audience is unchanged.
- The duration case, if confirmed.

## 7. 5PR-05 — First-run resume loses an unsaved preset pick

### Defect
`on_screen_resume` (`guided_first_run.py:255-270`) checks `_current_form_dirty()` only for the current step. It then reloads every step and re-baselines the steps it believes are clean.

Reproduced: choose OpenAI on `ai-provider` and continue to `provider-config`, so the preset fills the fields. Leave the wizard and come back.
- The AI choice reverts to the durable Ollama.
- `provider-config` shows a false dirty state.
- Discard restores the stale preset model.
- A later Save can overwrite a change saved elsewhere.

The FPR-09 evidence line ("preserves dirty steps") is contradicted.

### Required behavior
On resume, any step whose widgets differ from its baseline counts as dirty, not just the current step. Its widgets, including the AI choice that drives a later step's preset, survive the reload. Either refuse the reload with the existing status, or reload only the clean steps. Choose one, and make the AI choice and its preset baseline move together (as FPR-01 does for Discard).

### Acceptance
Real-input pilot reproducing the scenario above. After resume:
- the AI choice and the provider fields still show the unsaved pick;
- Discard on `provider-config` restores the durable values and the matching AI choice;
- durable bytes are unchanged throughout.

## 8. 5PR-06 — Slash fallback garbles JSON and code

### Defect
The slash-in-password fallback (`diagnostics.py:98-109`) cuts its token only at whitespace, so it reads across quotes, commas and parentheses. Reproduced:
- `{"url":"http://localhost:8080/x","email":"a@b.com"}` becomes `{"url":"http://[REDACTED]@b.com"}`.
- `fetch('http://api:8080/v1/x').catch(e=>log('a@b.com'))` is garbled the same way.

Nothing leaks, but diagnostics and logs are corrupted.

### Required behavior
Bound the fallback token at characters that cannot appear unencoded in a URL as typically quoted: `"`, `'`, `,` and `)`. Fix it together with 5PR-01 so the two changes are designed as one scan, and keep 5PR-01's leak cases redacted. Document the remaining known trade-off (`host:8080/@scope/pkg`).

### Acceptance
Both inputs above round-trip unchanged. Every 5PR-01 and fourth-cycle matrix row still passes.

## 9. 5PR-07 — Remaining legacy crashes and mislabelled outcomes

### Defect
The FPR-02 sweep (recorded as "20 unguarded actions"; there are 19 decorated actions) missed these:

- `research_screen.py:101-150`: save, analyze, search, ignore and research-all have no error handling.
- `transcript_review_screen.py:585-591`: `action_export` catches only `RuntimeError`, so an `OSError` from the export write crashes the app. `regenerate_turn` (`:573`) is similarly narrow.
- `preflight_screen.py:318-327`: `preflight_controller.build` is outside the `try`, and `sqlite3.Error` (a locked database) is not caught.
- `hosts_screen.py:208` (`action_save_host`) and `:309` (`action_save_relationship`) catch neither `sqlite3.Error` nor `OSError`.

`screen_guard.report_service_errors` wraps the service call and the screen refresh together. When the save succeeds and the refresh raises, the user is told "Source not added" or "Project not created" even though it was. This affects `tui.py:124-134` and `:298-312` and `hosts_screen.py:191-206`.

After a CAS conflict, the legacy Episode Plan screen says to reload, but it has no reload action. The screen is cached and `on_mount` does not re-run, so the only way to see the newer plan is Regenerate, which replaces it.

### Required behavior
1. Every legacy action that calls a service catches the shared error set and keeps the app alive with a sanitized status. Re-run the sweep with a mechanical method, for example an AST walk or grep for `self._app.service`, `composition.` and controller calls inside `action_*`. Record the exact count and list.
2. The guard distinguishes "service failed" from "succeeded, but refreshing the view failed". The second says the change was saved and the view could not be refreshed.
3. The legacy plan screen gets a Reload action (or reloads on `on_screen_resume`) that shows the stored plan without regenerating, and the conflict status names it.

### Acceptance
- Real-click or fault-injection tests for each listed action. Each fails on the baseline where the baseline crashes.
- A partial-success test: the service succeeds, the refresh raises, and the status says the change was saved.
- A plan-screen test: conflict, then Reload, then the newer plan is shown and the stored plan is unchanged.

## 10. 5PR-08 — Pre-existing sanitizer gaps

These leaks predate this cycle. All were reproduced with canaries:

- One-word keys with no separator: `apikey=`, `accesstoken=`, `clientsecret=`, `passwd=`.
- A PEM body after `private_key: -----BEGIN … PRIVATE KEY-----`.
- Python `bytes` header reprs, e.g. `b'Authorization': b'Bearer CANARY9x'`.
- Unclosed quoted values: `{"api_key": "CANARY9x` and `{'password': 'CANARY9x`.
- A credential URL cut before its `@` by the input cap.
- A fully percent-encoded non-HTTP URL: `postgres%3A%2F%2Fuser%3ACANARY9x%40db`.
- A secret in a custom-scheme fragment: `myapp://cb#state=1,code=CANARY9x`.

The matrix row "capped input cut mid authorization" is vacuous because the canary sits after the cap. Move the canary so the cut happens inside the secret.

### Required behavior
Fix each gap, or record it as accepted with a reason. Every fix gets a canary row that fails on the baseline, plus a benign row showing it does not over-redact (for example `passwd` in prose, or a `-----BEGIN CERTIFICATE-----` public block).

## 11. 5PR-09 — Cross-process lock aliasing

FPR-16 resolved the in-process re-entrancy key, but `_open_advisory_lock` (`user_config.py:598-603`) still builds the lock file from `self.path.parent` and `self.path.name` without resolving them. Two processes that reach a symlinked config through different paths lock different files, so they don't exclude each other. Derive the lock file from the resolved path, and test with two `UserConfigStore` instances on aliased paths in separate processes (or file descriptors), checking that they exclude each other. Keep `O_NOFOLLOW` on the lock file itself.

## 12. 5PR-10 — Residuals and latent defects

1. **FPR-13 residuals:**
   - `EpisodeSetupScreen` reads the database through `_configuration`, `_host_ids` and `_planning_assignment` outside any handler (`episode_setup_screen.py:118-125`, `refresh_summary:163`). A locked database crashes the screen.
   - Database errors in the planning block are attributed to the provider via `sanitize_provider_error` (`:149-151`).
   - `action_quick_deep_dive` (`:88-103`) has no handling around `quick_deep_dive` or `load_configuration`.
   - A stale `host_order_notice` can reappear on a later step.
2. **FPR-14 residual:** `load_plan` reads twice, and a concurrent delete between the reads gives an `IndexError`. It is caught, but the user sees a generic message. Make it one read, or map it to the typed conflict.
3. **FPR-07 residual:** the `edit_segment` docstring still describes the pre-FPR-07 contract. The evidence line "legacy and guided callers pass it" is vacuous for guided, which has no approve caller. Correct both.
4. **Discard restore fallback** (`wizard_shell.py:509-519`) assigns `Select.BLANK` to Selects that may have `allow_blank=False`. This is unreachable today. Route it through `_reset_select`.
5. **Create Host:** `_last_created_host_id` is never reset, so the comment that it is scoped to the double-submit window is overstated. Reset it when the form changes, or fix the comment.
6. **Picker:** a picker change under a prompt is ignored but not reverted when `_loaded_host_id is None`. Revert it, or document why that state can't show a picker.

## 13. 5PR-11 — Test quality

1. **FPR-03:** the free-text audience test must press Save after resume (the spec's no-op Save) and assert the stored audience is unchanged. Resume through real input, not `action_navigate("resume")`.
2. **FPR-04:** assert the user-visible status, not only the missing-baseline flag. Add a case showing that the first option adopted as the baseline is not written by a later Save the user didn't ask for.
3. **FPR-05 and FPR-11:** assert the visible status and that the transition runs exactly once. Replace direct calls with real input where the guard allows it; otherwise justify each in a comment.
4. **FPR-09:** add the 5PR-05 non-current-step case.
5. **FPR-17:** `test_noop_returns_the_record_it_compared_against` passes with the fix reverted. Make it discriminating by having another writer bump the revision between the comparison and the return.
6. **FPR-18:**
   - Convert the remaining `BUTTON_SETTLE_SECONDS` sleeps to condition waits where an observable condition exists, and document the debounce where it doesn't.
   - Give the `prior_wizard_destination` test its justification comment.
   - Make `type_into` clear through key presses rather than `widget.value = ""`, or document why.
7. **FPR-100:** the CI path check validates file paths only. Extend it to `file::node` ids (collect with `pytest --collect-only -q`), so a renamed test function is caught.
8. **Mutation evidence:** for each 5PR fix, the ledger records the failing count with the fix reverted, including for review-fix commits.

## 14. 5PR-12 — Process and documentation reconciliation

1. **`docs/ARCHITECTURE.md:230`** says a cancel request on any "pending/running/paused" run blocks a new run. The code and `GENERATION_RUN_SELECTION_POLICY.md` exempt paused runs. Fix it, and update it again for the 5PR-02 design.
2. **Fourth-cycle TODO.** Add dated annotations and ledger corrections only; do not uncheck anything.
   - Line 63 says "parametrized over pending/running/paused"; note the paused exemption.
   - FPR-02 says "20 unguarded actions"; the count is 19. Point to 5PR-07.
   - FPR-03 audit: note that membership guards avoid the crash but not the rewrite. Point to 5PR-04.
   - FPR-04: "No step has a generic loader hook" is wrong. `_load_episode_form`, `_load_project_form`, `_load_existing_setup` and `_refresh_research_choice` exist. Note what the implementation actually does: the first option becomes the clean baseline.
   - FPR-09: note 5PR-05.
   - FPR-000: "each test file failed on baseline" is overstated, because some matrix rows pass on the baseline.
   - Ledger rows FPR-06, 08 and 17 say "review-fix commit". Replace with `e55b78f`.
   - The FPR-08 note names `_split_userinfo`; the function is `_userinfo_end`.
   - The reviewer timing "worst 0.6 s" should be 1.46 s.
   - The wheel build and smoke ran on `040fb74`, before `e55b78f`.
   - Record the head `96a5b54` run 38694930846.
   - Add a "Post-closeout review 2026-10-15" note pointing to this spec for FPR-02, 03, 04, 06, 08, 09, 17 and 910.
3. **User guide and policy doc:** the cancel command and the stopping-run message match 5PR-02.
4. **Final qualification at the exact head**, after the last `src/` change:
   - `uv lock --check`
   - ruff format and lint
   - mypy
   - full pytest count
   - `uv build`
   - fresh-venv wheel smoke, including one redaction check from 5PR-01
   - green CI on both jobs, with run and job IDs

   If any commit touches `src/` after this step, repeat the whole step.
