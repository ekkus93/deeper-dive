# Deeper Dive TUI — Sixth Post-Review Remediation Specification

**Created:** 2026-10-15 (America/Los_Angeles)  
**Status:** Not started  
**Reviewed `master` baseline:** `44970a9` (fifth cycle closed; code head `d1952b4`; line references below are valid against `44970a9`)  
**Companion authoritative implementation checklist:** `docs/DEEP_DIVE_TUI_SIXTH_POST_REVIEW_REMEDIATION_TODO_2026-10-15.md`  
**Predecessor (historical, do not rewrite checked state):** `docs/DEEP_DIVE_TUI_FIFTH_POST_REVIEW_REMEDIATION_TODO_2026-10-15.md` and its spec  
**CI at baseline:** run 38739107751 on `44970a9` green. Run 38735849872 on `d1952b4` green (quality 116424819234, fresh-machine 116424818691). Full local check on the `d1952b4` tree: 2,538 passed.

## 1. Executive summary

Three independent reviewers carried out a read-only review of the completed fifth post-review cycle (every box ticked). They traced the production code without the implementer's conclusions, reran the targeted tests (all pass), ran each new test row against the baseline `diagnostics.py`, reverted selected fixes to check that tests discriminate, and wrote throwaway reproducers.

Much of the fifth cycle holds up:
- `get_plan_with_segments` is a single statement and handles zero-segment plans.
- `tolerate_refresh_errors` keeps "saved" when only the refresh fails.
- String-form model overrides, the shared "Custom" choice, and the first-run dirty-step refusal work.
- The no-op revision, stale-notice, Create Host window and picker-revert tests fail when their fixes are reverted.
- Sanitizer running time is linear (worst about 0.9 s over ~35 adversarial shapes at the 262,144-character cap).
- The evidence ledger matches git and CI.

The review nevertheless found that the new `episode cancel` path can execute the whole pipeline, that credential URLs still leak in several terminator combinations, that two legacy screens still crash the app on a locked database, a new stored-data rewrite introduced by the review-fix commit `d1952b4`, and ticked boxes whose evidence notes admit the work was not done.

| ID | Priority | Status | Topic | Main production surface |
| --- | --- | --- | --- | --- |
| 6PR-01 | High | Reproduced | Lost update of run control flags: `episode cancel` can execute every remaining stage; any stale stage write can erase a cancel or pause request | `pipeline.py`, `storage/run_repositories.py`, `cli.py` |
| 6PR-02 | High | Reproduced | Credential URL leaks when the password combines terminators with `@`, `/`, `,`, `)` or quotes; the numeric-password gap is wider than recorded | `diagnostics.py` |
| 6PR-03 | High | Reproduced | Episode Library actions and mount, and Generate (preflight) mount, crash the app on a database error; the 5PR-07 sweep cannot see them | `episode_library_screen.py`, `preflight_screen.py`, `tests/test_fifth_post_review_legacy_screens.py` |
| 6PR-04 | Medium | Reproduced | An empty stored technical depth or audience is rewritten to a preset by a no-op Save (regression from `d1952b4`) | `wizard_shell.py`, `guided_new_deep_dive.py` |
| 6PR-05 | Medium | Reproduced (1, 2); suspected (3, 4) | Legacy outcome mislabels and plan-screen crash: transcript regenerate, Quick Deep Dive partial success, Reload Plan on a zero-segment plan, Reload discarding unsaved edits | `transcript_review_screen.py`, `episode_setup_screen.py`, `episode_plan_screen.py` |
| 6PR-06 | Medium | Reproduced | Bytes and tuple header reprs, and other credential shapes, still leak | `diagnostics.py` |
| 6PR-07 | Low | Reproduced | Over-redaction from the 5PR-01 loose form; stale 5PR-06 docstring | `diagnostics.py` |
| 6PR-08 | Low | Reproduced | Model-override robustness: setup screen silently drops valid overrides; `null` crashes the CLI; no repair path outside the legacy screen | `episode_setup_screen.py`, `episode_config.py`, `cli.py` |
| 6PR-09 | Low | Source-verified / reproduced | Residuals: Discard fallback baseline, lock-file side effect at a dangling symlink target, sibling two-step plan reads, cancel refusal placeholder, TUI monitor cancels only the latest run | `wizard_shell.py`, `user_config.py`, `plan_validity.py`, `conversation_generation.py`, `composition.py`, `run_repositories.py`, `generation_monitor.py` |
| 6PR-10 | Medium (quality) | — | Fifth-cycle tests that do not check what their item claims, and missing required tests | `tests/` |
| 6PR-11 | Process | — | Reconcile the fifth-cycle TODO (boxes ticked for work that was not done); re-qualify at the exact head | fifth-cycle TODO, docs |

"Reproduced" means a reviewer's throwaway script demonstrated the failure (scripts were not committed; rewrite them as permanent regression tests). "Source-verified" or "suspected" means the defect follows from reading the code; the first step is a deterministic reproducer that fails on the baseline. If a reproducer disproves a finding, record the evidence and a narrowly justified N/A rather than deleting the task.

## 2. Governing execution contract

Everything in the fifth-cycle contract (spec §2) still applies: work on current `master`; one task per commit with the task ID; no `Co-Authored-By` trailers; push only after `./scripts/check.sh` exits 0 with an `N passed` line; exact-head CI is part of done; test first at the highest practical boundary; sweep siblings; review fixes are tested, swept and mutation-checked; any `src/` change after final qualification re-opens it; stored-data compatibility; real input means real input. In addition:

- **A deviation is not a tick.** If a subtask is implemented differently from its wording, or not at all, its box stays unchecked and is marked `N/A (deviation):` with the reason, or the box is reworded in the same commit with the reason recorded. The fifth cycle ticked 5PR-02's lease/`--force` box and 5PR-11's FPR-04 Save-after-adopt box while its own notes said neither was done.
- **Discriminating rows only.** Every canary or regression row claimed for an item must fail on the baseline. Rows that already pass on the baseline are labelled "pre-existing coverage" in the test file and the ledger, and do not count as evidence for the fix.
- **Accepted gaps live with the tests.** An accepted sanitizer gap is recorded as an `xfail(strict=True)` row (or an explicitly named "accepted" row) in the matrix test file, as well as in the ledger, so a later fix flips it visibly.
- **No wall-clock thresholds that can flake.** Linearity checks compare growth (for example, time at 2× size against 1×) or use a generous ceiling with the measured worst case recorded in the ledger.

## 3. 6PR-01 — Lost update of run control flags

### Defect
`GenerationRunRepository.update` (`storage/run_repositories.py:146-160`) writes `pause_requested` and `cancel_requested` from the caller's in-memory record. The pipeline's `_update` (`pipeline.py:227-248`) copies those flags from the record it read at the start of the stage. A control request written by another process between that read and the write is silently erased.

The fifth cycle's `episode cancel` (`cli.py:380-402`) makes this much worse. It calls `request_cancel` and then `pipeline.run(run.id)` in the CLI process. If a live worker's stage write lands in between, the flag is back to 0, and `pipeline.run` executes every remaining stage in the CLI process. It prints `state: completed` and exits 0. The reviewer reproduced this with all 8 stages executed. The same lost update affects the TUI's pause and cancel at any time.

### Required behavior
1. Control flags are only ever set by the request path and only ever cleared by an explicit transition that owns that decision: resume clears pause; reaching a terminal state may clear both. A stage-progress write must not clear a flag it did not read as set. Choose one design and document it in `docs/GENERATION_RUN_SELECTION_POLICY.md`, for example:
   - `update()` does not write the flags at all, and dedicated statements set or clear them; or
   - the write uses `cancel_requested = MAX(cancel_requested, ?)` (and the same for pause, except in the resume transition); or
   - an optimistic `modified_at`/revision check that re-reads and re-applies on conflict.
2. A stage write must not move a run out of `cancelled` (or any terminal state) set by another writer. Guard the state transition in SQL (`WHERE id=? AND state IN (...)`), and treat zero rows updated as "someone else finalized it".
3. `episode cancel` finalizes with a single conditional statement, for example `UPDATE generation_runs SET state='cancelled', cancel_requested=1, modified_at=? WHERE id=? AND state IN ('pending','running','paused')`. It must not call `pipeline.run` or any executor. Emit the same "cancelled" event the pipeline emits, and print the resulting record.
4. Sweep every writer of `generation_runs` (`grep -n "generation_runs" src/`) and record each one.

### Acceptance
- DB-level regression: a stale record write between `request_cancel` and the next read leaves `cancel_requested=1`. It fails on the baseline.
- CLI regression: a stage write injected between the CLI's request and its finalize; no stage handler runs (use a recording fake handler), the run ends `cancelled`, and exit code 0. It fails on the baseline.
- The same for pause: a stale stage write does not clear a pause request, and resume still clears it.
- A stage write after another writer set `cancelled` does not change the state.
- The concurrent-start thread test still yields one run.

## 4. 6PR-02 — Credential URL leaks with terminator combinations

### Defect
`_userinfo_end` (`diagnostics.py:95-149`) has three forms (authority, slash-in-password, terminator-in-password). Each form rejects some characters that the others do not cover, so these combinations leak (output unchanged unless shown):

- `https://user:p@a#ssCANARY9x@host/x` → `https://[REDACTED]@a#ssCANARY9x@host/x` (the authority form takes the first `@` because the authority stops at `#`)
- `https://user:pa/ss?CANARY9x@host/x` and `https://user:CANARY9x/x?y@host` (the slash form rejects any `?` after the colon; the loose form rejects `/`)
- `https://user:pa/ss'CANARY9x@host/x` and `https://user:pa/ss"CANARY9x@host/x`
- `https://user:pa#ss,CANARY9x@host`, `https://user:CANARY9x?)x@host`, `https://user:CANARY9x/x)y@host` (the loose window ends at `,` and `)`)
- any password longer than `_USERINFO_WINDOW` (1024) that contains a terminator
- `https://user:8#CANARY9x@host`, and generally any password whose text before the first terminator is all digits, such as `2024#Summer`. The fifth-cycle ledger records only "a purely numeric password followed by `?`/`#`".

### Required behavior
1. Redact the last `@` that is followed by a host and preceded by `user:` with no whitespace, whenever the text between the scheme and that `@` contains a `:`, unless the text before the first terminator is a genuine `host:port` (a host followed by `:` and 1-5 digits, then `/`, `?`, `#` or end). Choose the rule deliberately, document its precedence in the docstring, and keep it linear.
2. Re-decide the numeric-password case. `https://user:8#CANARY9x@host` and `https://host:8080#mail@b.com` have the same shape (`word:digits#…@host`), so one of them must lose. Options: fail closed (redact both, garbling the benign fragment-email case), or use a tie-breaker such as "the text after the terminator contains no `=`, `/` or `&`" or "the word before the colon has no `.`" (real hosts usually have a dot; `localhost` is the exception). Decide, document the precedence, and test both directions. Whatever stays accepted is named as a shape class, not one example.
3. For the window: a userinfo longer than the window fails closed (redact up to the window's last `@`) rather than passing through.
4. Every shape above becomes a canary row in the matrix, plus its JSON and Python-repr embedding. The fifth-cycle benign rows (`host:8080?email=a@b`, `host:8080#mail@b.com`, `/@scope`, JSON and code rows) stay unchanged.

### Acceptance
Each shape is redacted through `redact()`, `sanitize_exception_message()` and the CLI error path (a test that runs the CLI with a failing fake that raises a message containing the shape). Linear at the cap, recorded as described in §2.

## 5. 6PR-03 — Legacy screens that still crash the app

### Defect
- `EpisodeLibraryScreen` (`episode_library_screen.py`): `action_duplicate_selected` (`:257`) has no guard; `action_confirm_delete` (`:289-307`) catches only `KeyError`; `refresh_library` on mount and `_selected()` are unguarded. A locked database (`sqlite3.OperationalError`) during navigation to `library` (key `6`) or during Duplicate or Delete kills the app.
- `PreflightScreen.on_mount` (`preflight_screen.py:307-308`) calls `refresh_preflight` unguarded, so opening Generate while `PreflightController.build` raises crashes the app. Only `action_generate` was guarded.
- The 5PR-07 sweep test (`test_every_legacy_service_action_is_guarded_or_reviewed`) has blind spots: `_SCREEN_FILES` omits `episode_library_screen.py`; the controller marker match is case-sensitive; `_REVIEWED` exempts whole classes (`EpisodePlanScreen`, `EpisodeSetupScreen`) rather than named methods; mount-time `refresh_*` methods are not checked.

### Required behavior
1. Guard every Library action and the mount refresh with `report_service_errors`, and use `tolerate_refresh_errors` where a service call succeeded and only the refresh failed (Duplicate, Delete).
2. Guard `PreflightScreen.on_mount`'s refresh, and every other `on_mount`/`on_screen_resume` that calls the service, so a failure shows a status and leaves the app running.
3. Make the sweep test discover legacy screen files rather than list them (every module defining a `Screen` subclass that is not `guided_*`), match markers case-insensitively, exempt named methods with a reason rather than whole classes, and include `on_mount`/`on_screen_resume` and any `refresh_*` called from them.

### Acceptance
Pilot tests with a fake that raises `sqlite3.OperationalError` show the status and `app.is_running` for: navigating to Library, Library Duplicate, Library Delete confirm, navigating to Generate. Each fails on the baseline. The sweep test fails on the baseline (it finds the Library actions once the file is included).

## 6. 6PR-04 — Empty stored depth or audience rewritten by a no-op Save

### Defect
`WizardShell._show_stored_choice` returns early when the stored value is empty (`wizard_shell.py:349-350`, added in `d1952b4`), and `GuidedNewDeepDive` skips it when the project audience is empty (`guided_new_deep_dive.py:77`). The Select keeps its default preset. The CLI accepts empty values (`episode configure --depth "" --audience " "` exits 0 and stores `""`). Guided resume followed by a title-only Save stores `technical_depth='balanced'` and `audience='general'`.

Suspected: because the helper returns early, a Select that already shows another episode's value keeps it when the form is reloaded for an episode with an empty value.

### Required behavior
1. Decide, and document in the helper's docstring, what an empty stored value means. Recommended: an empty stored value is preserved by a no-op Save. Show it as an explicit "(not set)" option (or a blank Select where the control allows blank), so the control is honest and the durable value is not rewritten.
2. The load path always sets the Select from the stored value, never leaving a previous value in place.
3. Sweep every `_show_stored_choice` caller and every guided Select loaded from stored data.

### Acceptance
Real-input pilot: CLI stores `""` depth and `" "` audience; guided resume; title-only Save; the stored depth and audience are unchanged. It fails on the baseline. If the stale-value case is reachable, a test for it; otherwise an N/A with evidence.

## 7. 6PR-05 — Legacy outcome mislabels and plan-screen crash

1. **Transcript regenerate (reproduced).** `action_regenerate_turn` (`transcript_review_screen.py:573-584`) calls `refresh_review` outside `tolerate_refresh_errors`. A successful `repair_turn` followed by a refresh that raises `sqlite3.OperationalError` shows "Regeneration failed: database is locked". Wrap the refresh so the status keeps "Regenerated…" with the refresh-failed suffix. Sweep every legacy action for a service call followed by an unwrapped refresh.
2. **Reload Plan on a zero-segment plan (reproduced).** `_load_selected` (`episode_plan_screen.py:251`) indexes `plan.segments[self.selected_ordinal]` outside the try. A plan with no segment rows raises `IndexError`. Clamp `selected_ordinal`, handle an empty plan with a visible status, and guard every caller of `_load_selected`.
3. **Quick Deep Dive partial success (suspected).** `action_quick_deep_dive` (`episode_setup_screen.py:84-95`): if `quick_deep_dive` creates the episode and then `load_configuration` or `_planning_assignment` raises, the status says "Quick Deep Dive failed" though the episode exists and is current. Report "Episode created; planning could not start: …".
4. **Reload Plan discards unsaved edits (suspected).** Reload overwrites the segment Inputs without warning. Either confirm first when the inputs differ from the loaded plan, or record why reload-after-conflict must discard (the stored plan wins) and say so in the status.

### Acceptance
A test per item that fails on the baseline (or a justified N/A for the suspected items). Tests use a real stored plan, not a MagicMock controller, and do not patch out `_load_selected` or `_render_plan`.

## 8. 6PR-06 — Bytes, tuple and other credential shapes

### Defect
These leak (and leaked before the fifth cycle). The fifth cycle's "bytes header reprs" rows passed on the baseline only because the old Bearer rule redacts `Bearer` values.

- `{b'Authorization': b'Basic C'}`, `{b'x-api-key': b'C'}`, `{'api_key': b'C'}`
- `[(b'authorization', b'Basic C')]`, `[('x-api-key', 'C')]`, `[('Authorization', 'Basic C')]`, `(('cookie', 'a=C'),)`
- `pwd=C`, `auth=C` (the URL key set has them; the plain assignment classifier does not)
- `--api-key C`, `--password=C`, `<password>C</password>`
- `password="pa ssC"` → `password=[REDACTED] ssC"`
- escaped JSON inside a string: `"{\"apiKey\":\"C\"}"` and `"\"password\" : \"C\""`

### Required behavior
1. The quoted-mapping rules accept an optional `b` prefix on keys and values, and the `(key, value)` tuple form, for every sensitive key.
2. One sensitive-key set is shared by the assignment, mapping, URL-query and CLI-flag rules.
3. A quoted value is redacted to its closing quote (including spaces), with the 5PR-08 unclosed-quote rule as the fallback.
4. Escaped-quote JSON is handled, or recorded as an accepted gap row (§2).
5. Benign rows: `{b'content-type': b'json'}`, `('accept', 'text/html')`, `--verbose`, `auth_method=oauth` (decide whether an `auth*` prefix match is wanted and document it).

## 9. 6PR-07 — Over-redaction and stale docstring

1. The 5PR-01 loose form checks for `:` over the whole userinfo, not only before the first terminator. These garble (never leak): `https://example.com?q=a:b@c`, `https://example.com#a:b@c`, `http://h:abc#frag@x.com` → `…[REDACTED]@…`. Restrict the colon test to the part before the first terminator, consistent with 6PR-02's rule; add the three as benign rows.
2. The PEM pass wipes prose that names a header (`use '-----BEGIN PRIVATE KEY-----' header` → `use '[REDACTED PRIVATE KEY]`). Either require a base64 body line after the opener, or record it as an accepted fail-closed row.
3. The `_userinfo_end` docstring (`diagnostics.py:114-115`) still says `scheme://host:8080/@scope/x` is redacted; since `d1952b4` it is not. It omits the real trade-off `host:8080/v1/models/gpt@latest` → `https://[REDACTED]@latest`. Correct it after 6PR-02.

## 10. 6PR-08 — Model-override robustness

1. `_existing_model_overrides` (`episode_setup_screen.py:246`) calls `existing.normalized()` on the whole configuration. An invalid field elsewhere (for example `source_overrides={"s1": 1}`) makes it return `{}`, so the next legacy Save wipes valid model overrides. Normalize only the overrides, and when stored overrides are dropped as invalid, tell the user which role was dropped.
2. A stored `"model_overrides": null` (or a top-level string) raises an untyped `TypeError` from `episode_config.py:250`. Load must raise a typed, field-naming error (or treat `null` as empty; decide and document).
3. Repair path: with an invalid stored override, every CLI `episode configure` edit fails with exit 2, and the guided Save fails. Add a CLI repair (for example `episode configure --clear-model-override <role>` or `--clear-model-overrides`) and make the error message name it. The guided wizard either offers the same or its error names the CLI command.
4. Validation errors are a dedicated typed error (subclass of `ValueError` for compatibility) rather than a bare `ValueError`.

## 11. 6PR-09 — Residuals

1. **Discard fallback baseline (suspected).** On an `allow_blank=False` Select, `_reset_select` picks the first option, and `_remember_current_form()` then records it as the clean baseline (`wizard_shell.py:538-545`). The comment says "the control shows blank", and nothing forces the user to choose. Either keep the step dirty (or blocked) until the user picks, or fix the comment and record why adopting the first option is safe. Reproduce first.
2. **Lock side effect (reproduced).** For a config path that is a dangling symlink to `elsewhere/deep/target.json`, `save()` creates `elsewhere/deep/` and `.target.json.lock` there before raising `UserConfigError` (`user_config.py:600-606`). Reject the symlink before creating anything.
3. **Sibling two-step plan reads.** `plan_validity.py:45/67`, `conversation_generation.py:89/93` and `composition.py:579/584` read the plan and its segments separately. They fail safe today. Move them to `get_plan_with_segments` or record each as safe with the reason.
4. **Cancel refusal placeholder.** The refusal text contains a literal `<project_id>` (`run_repositories.py:99-100`), but the spec asked for the exact command. Either thread the project id into the message (the caller knows it) or have the CLI rewrite the message.
5. **TUI cancel reaches only the latest run.** The monitor (`generation_monitor.py:61`) shows the latest run when no run is selected, so a TUI user blocked by an older stopping run must use the CLI. Show the blocking run (or a notice naming the CLI command) in the monitor.
6. **Duration custom field (suspected, UX).** With 1830 s stored, the custom field shows 30; typing 30 keeps 1830 s. Decide and document (show `30.5`, or treat an edited field as authoritative).

## 12. 6PR-10 — Test quality

1. **FPR-04 Save-after-adopt.** The fifth cycle ticked this without a test. Write it: a Discard fallback adopts the first option; a later Save the user did not ask for does not write that option (or the step blocks until the user chooses, per 6PR-09.1).
2. **5PR-02 tests.** `test_cli_cancel_rejects_a_run_of_another_episode` uses the id `"missing"`; use a real run of another episode. `test_cli_cancel_never_executes_a_stage` must discriminate on stage execution (a recording handler), not only on which run was targeted. Folds into 6PR-01's acceptance.
3. **5PR-07 tests.** Add the missing fault test for transcript regenerate; add `OSError` cases for host save and relationship save; the hosts "stored name unchanged" check must use a real `update_host`, not a mock. The Reload Plan test uses a real stored plan and a real conflict and asserts the stored plan is unchanged.
4. **5PR-09 test.** The child process must report "acquired" or "blocked" explicitly; check its output and exit code, so a slow import or a crashed child cannot pass.
5. **5PR-05 test.** Follow the spec's exact path (Continue to `provider-config`, leave, return) and compare the durable config bytes.
6. **5PR-08 rows.** Label the bytes Bearer rows and the authorization cap row as "pre-existing coverage"; move the accepted gaps into the matrix file as strict-xfail rows.
7. **5PR-01 rows.** Add the JSON embedding for every shape, not only `#`, and the CLI error-path check.
8. **Fragile patterns.**
   - `test_fourth_post_review_prior_wizard_destination.py:65-78` patches `type(app).action_navigate` without `try/finally`; use `monkeypatch` or `try/finally`.
   - The Create Host test in `test_fifth_post_review_residuals.py` falls back to `picker.value = created`; remove the fallback or justify it.
   - Remove the unused `real` and `calls` in the partial-success test.
   - The sanitizer `< 4.0` s assertions follow §2.
9. **CI node-id check.** Handle `file::Class::method` ids (none in `ci.yml` today, but the check would report them as missing).

## 13. 6PR-11 — Process and documentation reconciliation

1. **Fifth-cycle TODO.** Add dated annotations and ledger corrections only; do not uncheck anything.
   - 5PR-02 lease/`--force` box: ticked, but neither was implemented; point to 6PR-01 and the policy doc.
   - 5PR-11 FPR-04 box: ticked, but no Save-after-adopt test; point to 6PR-10.1.
   - 5PR-01: worst-case timing was not recorded, and there was no CLI-path test; point to 6PR-02.
   - 5PR-01 accepted numeric-password wording is narrower than the real gap.
   - 5PR-08: bytes header reprs not fixed (rows passed on the baseline); accepted gaps were not recorded in the matrix file.
   - 5PR-07 sweep note omits Episode Library, preflight mount and transcript regenerate; point to 6PR-03 and 6PR-05.
   - 5PR-04: the empty-value rewrite introduced by `d1952b4`; point to 6PR-04.
   - 5PR-911: the review missed 6PR-01, 6PR-03 and 6PR-05.1.
   - Record the exact-head run 38739107751 on `44970a9`.
   - Add a "Post-closeout review 2026-10-15 (sixth)" note pointing to this spec.
2. **Policy doc and user guide** match 6PR-01's control-flag rules and the cancel command, including that cancel no longer executes anything.
3. **Final qualification at the exact head**, after the last `src/` change:
   - `uv lock --check`
   - ruff format and lint
   - strict mypy
   - full pytest count
   - `uv build`
   - fresh-venv wheel smoke, including one 6PR-02 redaction check, one 6PR-06 check, and `deeper-dive episode cancel --help`
   - green CI on both jobs, with run and job IDs

   If any commit touches `src/` after this step, repeat the whole step.
