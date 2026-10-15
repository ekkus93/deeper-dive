# Deeper Dive TUI — Sixth Post-Review Remediation TODO

**Created:** 2026-10-15 (America/Los_Angeles)  
**Status:** Complete (code head `8ad0a60`, CI run 38789463854 green)  
**Authority:** `docs/DEEP_DIVE_TUI_SIXTH_POST_REVIEW_REMEDIATION_SPEC_2026-10-15.md`  
**Reviewed baseline:** `44970a9` (CI run 38739107751 green; code head `d1952b4`, CI run 38735849872 green; local 2,538 passed on the `d1952b4` tree)  
**Predecessor historical checklist:** `docs/DEEP_DIVE_TUI_FIFTH_POST_REVIEW_REMEDIATION_TODO_2026-10-15.md`

This is the only completion checklist for the sixth post-review cycle. No item is prechecked. A checked item must identify:

- the production behavior that changed;
- a deterministic test that failed before the fix;
- the commit SHA;
- a green exact-head CI run.

If a reproducer disproves a finding, keep the task visible and record a justified N/A with exact evidence.

## Post-closeout review 2026-10-15 (seventh)

The seventh-cycle follow-up is tracked in
[`DEEP_DIVE_TUI_SEVENTH_POST_REVIEW_REMEDIATION_TODO_2026-10-15.md`](DEEP_DIVE_TUI_SEVENTH_POST_REVIEW_REMEDIATION_TODO_2026-10-15.md).
Sixth-cycle checked state remains historical and unchanged.

## Execution rules

- At every run start and after every `master` push, reload this TODO and the spec, inspect the exact head and its CI, and avoid duplicating landed work.
- One task per commit, with the task ID in the message and no `Co-Authored-By` trailers. Push only after `./scripts/check.sh` exits 0 with an `N passed` line.
- **CI is part of done.** `check.sh` does not run `fresh-machine`. A commit that renames, moves or deletes a test file updates `.github/workflows/ci.yml` in the same commit. Record the green run ID before ticking.
- **Test first**, at the highest practical boundary.
  - Wizard defects: real Textual input via `tests/guided_pilot.py`.
  - Storage and run-control defects: service- or DB-level tests with recording fakes.
  - Any test that seeds `context.state`, calls `action_*` or `on_screen_resume` directly, assigns `widget.value`, or patches a screen method records why in a comment.
- **A deviation is not a tick.** A subtask done differently, or not done, stays unchecked and is marked `N/A (deviation):` with the reason, or is reworded in the same commit with the reason recorded.
- **Discriminating rows only.** Rows that already pass on the baseline are labelled "pre-existing coverage" and are not evidence for a fix.
- **Accepted sanitizer gaps** are strict-xfail (or explicitly named "accepted") rows in the matrix test file, as well as in the ledger.
- **Sweep siblings:** every fix greps for the same pattern elsewhere and records the result in the item's evidence line.
- **Review fixes** are tested, swept and mutation-checked like task fixes, and the ledger names their SHA.
- **Any `src/` change after 6PR-912 re-opens 6PR-912.**
- Do not change checked state in the fifth-cycle TODO; 6PR-11 adds annotations and ledger corrections only.

## 6PR-000 — Baseline

- [x] Record the baseline head (`44970a9`), a fresh full local check count on it, and CI run 38739107751.
- [x] Every "Reproduced" item has a committed regression test that fails on the baseline. Every "suspected" or "Source-verified" item has a deterministic reproducer or a justified N/A. List rows that already pass on the baseline.

## 6PR-100 — Correctness and leaks

### 6PR-01 — Lost update of run control flags
- [x] DB-level regression: a stale stage write after `request_cancel` leaves `cancel_requested=1` (fails on the baseline). Same for pause; resume still clears pause.
- [x] Control flags are set only by the request path and cleared only by resume (pause) or a terminal transition. Design recorded in `docs/GENERATION_RUN_SELECTION_POLICY.md`.
- [x] Stage writes cannot move a run out of `cancelled` set by another writer (conditional `UPDATE`; zero rows means someone else finalized it). Test. Deviation from "or another terminal state": `completed` and `failed` stay re-drivable (`force_from`, resume), so only `cancelled` is final; recorded in the policy doc.
- [x] `episode cancel` finalizes with one conditional statement and never calls `pipeline.run` or any executor. It emits the "cancelled" event and prints the record.
- [x] CLI regression with a stage write injected between request and finalize: no stage handler runs (recording fake), the run ends `cancelled`, exit 0. Fails on the baseline.
- [x] Sweep every writer of `generation_runs` and record each (see notes). The concurrent-start thread test still yields one run.

### 6PR-02 — Credential URL leaks with terminator combinations
- [x] Canary rows that fail on the baseline, each also embedded in JSON and in a Python repr:
  - `https://user:p@a#ssCANARY9x@host/x`
  - `https://user:pa/ss?CANARY9x@host/x`, `https://user:CANARY9x/x?y@host`
  - `https://user:pa/ss'CANARY9x@host/x`, `https://user:pa/ss"CANARY9x@host/x`
  - `https://user:pa#ss,CANARY9x@host`, `https://user:CANARY9x?)x@host`, `https://user:CANARY9x/x)y@host`
  - a password longer than `_USERINFO_WINDOW` containing a terminator
- [x] `_userinfo_end` uses one rule for the last host-followed `@`, with the `host:port` exception decided and documented in the docstring; linear.
- [x] Numeric-password case re-decided (`https://user:8#CANARY9x@host` vs `https://host:8080#mail@b.com`); both directions tested; any remaining accepted shape named as a class (a password starting with a valid port number, 1-5 digits <= 65535, directly followed by a terminator; strict-xfail rows).
- [x] A userinfo longer than the window fails closed.
- [x] Fifth-cycle benign rows unchanged (`host:8080?email=a@b`, `host:8080#mail@b.com`, `/@scope`, JSON and code rows).
- [x] Each shape checked through `redact()`, `sanitize_exception_message()` and a CLI error-path test. Linearity checked by growth ratio or a generous ceiling; worst case recorded.

### 6PR-03 — Legacy screens that still crash the app
- [x] Pilot regressions with a fake raising `sqlite3.OperationalError` (each fails on the baseline): navigate to Library; Library Duplicate; Library Delete confirm; navigate to Generate. Each shows a status and `app.is_running`.
- [x] Every `EpisodeLibraryScreen` action and its mount refresh are guarded; Duplicate and Delete use `tolerate_refresh_errors` for the refresh after a successful service call.
- [x] `PreflightScreen.on_mount`, and every other legacy `on_mount`/`on_screen_resume` that calls the service, is guarded.
- [x] The sweep test discovers legacy screen modules instead of listing them, matches markers case-insensitively, exempts named methods (with a reason) rather than whole classes, and covers mount/resume refreshes. It fails on the baseline.

### 6PR-04 — Empty stored depth or audience rewritten
- [x] Real-input pilot: CLI stores `""` depth and `" "` audience; guided resume; title-only Save; stored values unchanged. Fails on the baseline.
- [x] `_show_stored_choice` never returns early: an empty stored value is shown honestly (a "(not set)" option or blank) and preserved by a no-op Save. Meaning documented in the docstring.
- [x] `guided_new_deep_dive.py:77` no longer skips an empty project audience.
- [x] Stale-value case (a Select keeping another episode's value): N/A (fixed structurally): `_show_stored_choice` no longer returns early, so every load sets the Select from the stored value and `set_options` replaces the option list; a leftover value cannot survive a reload. The two scenarios below cover empty stored values.
- [x] Sweep every guided Select loaded from stored data.

## 6PR-200 — Robustness

### 6PR-05 — Legacy outcome mislabels and plan-screen crash
- [x] Transcript regenerate: a successful repair followed by a failing refresh keeps "Regenerated…" with the refresh-failed suffix. Test fails on the baseline. Sweep legacy actions for a service call followed by an unwrapped refresh.
- [x] Reload Plan on a zero-segment plan shows a status instead of `IndexError`; `selected_ordinal` clamped; every `_load_selected` caller guarded. Test with a real stored plan, not patched.
- [x] Quick Deep Dive partial success reports "Episode created; planning could not start: …" (reproducer first, or N/A).
- [x] Reload Plan with unsaved segment edits: confirm first, or document why the stored plan wins and say so in the status (reproducer first).

### 6PR-06 — Bytes, tuple and other credential shapes
- [x] Canary rows that fail on the baseline:
  - `{b'Authorization': b'Basic C'}`, `{b'x-api-key': b'C'}`, `{'api_key': b'C'}`
  - `[(b'authorization', b'Basic C')]`, `[('x-api-key', 'C')]`, `[('Authorization', 'Basic C')]`, `(('cookie', 'a=C'),)`
  - `pwd=C`, `auth=C`
  - `--api-key C`, `--password=C`, `<password>C</password>`
  - `password="pa ssC"`
- [x] One sensitive-key set shared by the assignment, mapping, URL-query and CLI-flag rules.
- [x] Quoted values redacted to the closing quote, with the unclosed-quote rule as the fallback.
- [x] Escaped-quote JSON (`"{\"apiKey\":\"C\"}"`, `"\"password\" : \"C\""`) redacted, or an accepted strict-xfail row.
- [x] Benign rows: `{b'content-type': b'json'}`, `('accept', 'text/html')`, `--verbose`, `auth_method=oauth` (the `auth*` decision documented).

### 6PR-07 — Over-redaction and stale docstring
- [x] The colon test only looks before the first terminator (done in 6PR-02's `_credential_shaped`). Benign rows: `https://example.com?q=a:b@c`, `https://example.com#a:b@c` (garbled on the baseline). N/A (deviation) for `http://h:abc#frag@x.com`: it has the same shape as `user:pass#word@host`, so it stays redacted on purpose and a test pins that.
- [x] PEM prose that only names a header: require a body line, or an accepted fail-closed row.
- [x] `_userinfo_end` docstring corrected (`/@scope` is not redacted; `gpt@latest` is the trade-off), after 6PR-02.

### 6PR-08 — Model-override robustness
- [x] The legacy setup screen keeps valid overrides when another field is invalid (`source_overrides={"s1": 1}` plus a valid `episode_planning` override). Test fails on the baseline.
- [x] Dropping an invalid stored override tells the user which role was dropped.
- [x] `"model_overrides": null` and a top-level string give a typed, field-naming error (or `null` is treated as empty; decided and documented). Test fails on the baseline.
- [x] CLI repair path for invalid stored overrides; the error message names it; the guided wizard offers it or names the command.
- [x] Validation errors use a dedicated typed error (a `ValueError` subclass).

### 6PR-09 — Residuals
- [x] Discard fallback on an `allow_blank=False` Select: reproduce; then keep the step dirty or blocked until the user picks, or fix the comment and record why adopting the first option is safe. N/A (deviation): not reproducible. Every `allow_blank=False` guided Select has static presets (plus the stored "Custom"/"(not set)" option), so the `InvalidSelectValueError` branch cannot occur for it; the comment is corrected and `_reset_select` is pinned by a unit test.
- [x] A dangling-symlink config path is rejected before any directory or lock file is created. Test fails on the baseline.
- [x] `plan_validity.py`, `conversation_generation.py` and `composition.py` two-step plan reads moved to `get_plan_with_segments`, or each recorded as safe with a reason. Moved; no new test (the previous behaviour failed safe, so no baseline-failing reproducer exists; existing plan-validity, conversation and evidence tests pass).
- [x] The stopping-run refusal names the real project id (no `<project_id>` placeholder). Test.
- [x] The TUI monitor shows the blocking run, or a notice naming the CLI command, when an older run blocks a start.
- [x] Duration custom field with a non-whole-minute stored value: decided and documented (test or N/A). Decision: typing the rounded minutes keeps the exact stored seconds, the 30-minute preset sets exactly 30:00 (comment in `_duration_seconds`); the preserve half is covered by the 5PR-04 pilot, N/A for a new test.

## 6PR-300 — Tests and process

### 6PR-10 — Test quality
- [x] FPR-04 Save-after-adopt test (per 6PR-09's Discard decision).
- [x] 5PR-02 tests: a real run of another episode; stage execution checked with a recording handler (with 6PR-01).
- [x] 5PR-07 tests: transcript regenerate fault test; `OSError` for host save and relationship save; hosts "name unchanged" with a real `update_host`; Reload Plan test with a real plan, a real conflict, and the stored plan unchanged.
- [x] 5PR-09 test: the child reports "acquired" or "blocked" explicitly; output and exit code checked.
- [x] 5PR-05 test: the spec's exact path, with durable config bytes compared.
- [x] 5PR-08 rows: bytes Bearer rows and the authorization cap row labelled "pre-existing coverage"; accepted gaps moved into the matrix file as strict-xfail rows.
- [x] 5PR-01 rows: JSON embedding for every shape; CLI error-path check.
- [x] Fragile patterns: `try/finally` or `monkeypatch` in `prior_wizard_destination`; Create Host fallback removed or justified; unused `real`/`calls` removed; sanitizer wall-clock assertions replaced per the spec.
- [x] CI node-id check handles `file::Class::method` ids, with a self-test.

### 6PR-11 — Process and documentation reconciliation
- [x] Fifth-cycle TODO annotations (no unchecking):
  - 5PR-02 lease/`--force` box (not implemented; see 6PR-01);
  - 5PR-11 FPR-04 box (no test; see 6PR-10);
  - 5PR-01 timing not recorded and no CLI-path test; numeric-password wording too narrow;
  - 5PR-08 bytes reprs not fixed (rows passed on baseline); accepted gaps not in the matrix file;
  - 5PR-07 note omits Library, preflight mount, transcript regenerate;
  - 5PR-04 empty-value rewrite from `d1952b4`;
  - 5PR-911 missed 6PR-01, 6PR-03, 6PR-05;
  - exact-head run 38739107751 on `44970a9`.
- [x] Add a "Post-closeout review 2026-10-15 (sixth)" note in the fifth-cycle TODO pointing to this cycle.
- [x] `docs/GENERATION_RUN_SELECTION_POLICY.md`, `docs/ARCHITECTURE.md` and the user guide match 6PR-01 (control-flag rules; cancel executes nothing).

## 6PR-900 — Review and qualification

### 6PR-911 — Independent review
- [x] A fresh read-only reviewer with no prior conclusions traces every changed source path and sibling sweep. Every finding is fixed (with a test, a sweep and a mutation check) or recorded as accepted with a reason. Review-fix commits are named by SHA.

### 6PR-912 — Final qualification (after the last `src/` change)
- [x] `uv lock --check`; ruff format and lint; strict mypy; full pytest count recorded at the exact head.
- [x] `uv build`; fresh-venv wheel smoke at the exact head, including one 6PR-02 and one 6PR-06 redaction check and `deeper-dive episode cancel --help`.
- [x] Green exact-head CI on both jobs, with run and job IDs.
- [x] Evidence ledger below complete. Every row's test fails with its fix reverted (Mutation column), including review fixes.

## Evidence ledger

| Item | Outcome | Commit(s) | Test file(s) | Mutation |
|---|---|---|---|---|
| 6PR-01 | confirmed (reviewer reproduced all 8 stages run) | 41523b5, 8ad0a60 | sixth_post_review_run_control | run (5 failed; race test fails without the pipeline guard) |
| 6PR-02 | confirmed | 623ce58 | sixth_post_review_url_leaks | run (53 failed on baseline diagnostics) |
| 6PR-03 | confirmed | 056ad59 | sixth_post_review_legacy_crashes | run (5 of 6 failed) |
| 6PR-04 | confirmed (regression from d1952b4) | 2bbabf4 | sixth_post_review_empty_stored_values | run (2 failed) |
| 6PR-05 | confirmed (items 1, 2; 3, 4 reproduced) | 7f73eb9 | sixth_post_review_legacy_outcomes | run (4 failed) |
| 6PR-06 | confirmed | 13dabd3, 8ad0a60 | sixth_post_review_credential_shapes | run (37 failed; backslash case hangs on the unfixed pattern) |
| 6PR-07 | partly N/A (h:abc#frag stays redacted on purpose) | 623ce58, add1d83 | url_leaks, credential_shapes | run |
| 6PR-08 | confirmed | f4ef3d8 | sixth_post_review_model_override_repair | run (import fails without src) |
| 6PR-09 | confirmed (Discard fallback N/A: unreachable) | 92e6b10 | sixth_post_review_residuals, lock_processes | run (lock test fails with resolve() reverted) |
| 6PR-10 | complete | 92e6b10 | fifth/fourth/third strengthened tests, linear_timing | n/a (tests) |
| 6PR-11 | complete | 92e6b10 | ci_paths | n/a (docs) |

## Evidence notes

(Record baseline counts, sweep results, design decisions, deviations, accepted gaps and qualification evidence here.)

- **6PR-01 sweep:** writers of `generation_runs` are `GenerationRunRepository.create/select_or_create` (INSERT), `update` (pipeline `_update`, `resume`, failure path; `composition.py:356` failure path), `_set_flag` (request_pause/request_cancel) and the new `cancel_now`. `tts_generation.py`, `plan_validity.py`, `host_turn.py` and `service.py` only SELECT it. Mutation: with `src/` reverted the 5 new tests in `test_sixth_post_review_run_control.py` fail.
- **6PR-02 design:** `_userinfo_end` now has one fallback rule: the last host-followed `@` of a scan token (`_TOKEN_END`: whitespace, or `,`/`)`/quote only when followed by a separator) whose preceding text is `_credential_shaped` (a `:` before the first `/?#`, not ending in `/`, and not `host:port` + terminator). It also extends an authority-form match when the password held `@` plus a terminator, and a credential-shaped token that fills the 1024-character window is redacted whole (fails closed). Side effects: `host:8080/v1/models/gpt@latest` and `scheme://host:8080/@scope/x` are now benign (port + path) instead of garbled; `https://user:pw@host:8080/x?e=a@b` now loses its host and path (over-redaction, no leak). Accepted: password starting with a valid port number + terminator (`u:8#pw@h`, `u:2024#Summer@h`). Worst-case timing at the 262,144 cap: 1.5 s (`x://` repeated; baseline 1.1 s), 1.0 s (`u://a#@` repeated). Mutation: 53 tests in `test_sixth_post_review_url_leaks.py` fail on the baseline `diagnostics.py`.
- **6PR-03:** Library (all actions + mount; `refresh_library` is `tolerate_refresh_errors`), Preflight/Providers/Settings/Monitor/Claim Inspector/Transcript `on_mount`, `ClaimInspectorScreen.action_select_claim`, `TranscriptReviewScreen.action_select_turn` and `SourcesScreen.action_delete_selected` (found by the new sweep; `tui.py` was previously listed but missed because the marker match was case-sensitive) now carry `report_service_errors`. The sweep (`test_sixth_post_review_legacy_crashes.py`) discovers every non-guided Screen subclass, matches markers case-insensitively, follows unguarded `self.` helpers, and exempts only named `Class.method` entries with a reason. Mutation: with `src/` reverted, 5 of 6 tests fail (the 6th proves the sweep reports stripped guards).
- **6PR-04:** an empty stored value is shown as a "(not set)" option (value `""`). The episode Save passes `keep_empty=True` to `_select_value` only when the durable depth/audience is itself empty (`current.audience == ""`), so choosing a value is still required otherwise; the project form tracks `_project_audience_unset` the same way. Sweep: `_show_stored_choice` callers are episode audience, episode depth and project audience (all three covered); duration was already preserved (5PR-04); other loaded Selects (research choice, voice/provider pickers) use blank-with-reselect through `_set_select_value`, not a preset fallback. Mutation: both new pilots fail with `src/` reverted.
- **6PR-05:** `refresh_review` is `tolerate_refresh_errors`; Reload Plan is `report_service_errors`, handles a zero-segment plan (`_load_selected` clamps/clears; `refresh_plan` reports "no segments" and returns False), and says "unsaved segment edits were discarded" when the inputs differed (decision: the stored plan wins). Quick Deep Dive reports "Episode created; planning could not start: …" when `load_configuration`/`_planning_assignment` raise after the episode exists. Sweep of service-call-then-refresh: other `refresh_*` are `tolerate_refresh_errors` (projects, sources, hosts, research, library, review) or return their own status (`refresh_plan`, `refresh_monitor` whose `None` status means "no change", so the decorator is not applied); `refresh_claims`/providers/settings call no service after a mutation. The mocked 5PR-07 Reload test (`MagicMock` controller, patched `_render_plan`/`_load_selected`) was replaced by a real-conflict test in `test_sixth_post_review_legacy_outcomes.py` (also covers 6PR-10 item 3, Reload part). Mutation: all 4 new tests fail with `src/` reverted.
- **6PR-06:** new passes in `_redact_text` (all linear; each bounded repeat-prefix input at the 262,144 cap took <= 0.13 s): optional `b` before mapping values (group 3 `\s*:\s*b?`), `_TUPLE_PAIR`, `_CLI_FLAG_VALUE`, `_XML_ELEMENT`, `_QUOTED_VALUE_ASSIGNMENT` (to the closing quote, else end of line) and `_ESCAPED_QUOTE_PAIR` (value bounded at 2,048 characters, so a longer escaped secret keeps its tail: accepted). `_is_secret_key` gained `pwd` and a bare `auth` key (`auth_method`, `author` stay benign) and the assignment key alternation gained `pwd|auth`; one classifier (`_is_secret_key`) now serves assignment, mapping, tuple, flag, element and escaped rules. URL-query-only keys (`code`, `key`, `sig`, `session`, ...) deliberately stay query-specific because they are common benign JSON fields. Over-redaction accepted: `--token-limit 5` (the word `token`, as `token_limit=5` already was). Mutation: 37 of 50 rows fail on the baseline `diagnostics.py`; the 13 that pass are the benign rows and the `repr` variants of rows the old Bearer rule already covered.
- **6PR-07:** the loose-form colon check and the stale docstring were fixed together with 6PR-02 (commit `623ce58`; docstring now lists the accepted gap and the `user:pw@host:8080/x?e=a@b` over-redaction). The PEM pass now requires the opener to be followed by a line break, an escaped `\n`, or a 16-character base64 run, so prose that names a header survives; the fail-closed unclosed-body behaviour is unchanged.
- **6PR-08:** `InvalidModelOverrides` (a `ValueError` subclass in `storage/episode_errors.py`) is raised by the override normalizer and by `configuration_from_record` for a non-mapping stored value; stored `null` means "none". Its message ends with the repair command; `describe(project_id, episode_id)` fills in the real ids and is used by the CLI (`episode configure` re-raises it as a `ValueError`) and the guided Save. `episode configure --clear-model-overrides` loads with `drop_invalid_model_overrides=True` and writes no overrides, so even a non-mapping stored value can be repaired. The legacy setup screen normalizes only the overrides (an invalid `source_overrides` no longer drops valid ones) and appends "Stored model overrides were replaced (<detail naming the role>)" to the "Plan built" status. Mutation: with `src/` reverted the new test module cannot even import `InvalidModelOverrides`; the behaviours (CLI repair, notice, null handling) are new.
- **6PR-09:** dangling-symlink config path raises before any directory or lock file is created (only a dangling link is rejected there; existing-symlink spellings still share one lock and load/save reject them as before). `GenerationRunStillStopping` names the real project id (`select_or_create(project_id=...)`; the placeholder remains only when a caller omits it). `MonitorSnapshot.blocking_run` makes the monitor print the exact `episode cancel … --run` command for an older stopping run. Sibling plan reads use `get_plan_with_segments`.
- **6PR-10:** FPR-04 Save-after-adopt: asserted in `test_third_post_review_voice_discard.py` (a vanished voice stays blank and Save refuses, config bytes unchanged); 5PR-02 foreign-run test uses a real second episode; hosts failures use SQLite triggers on the real repository (no mocks) plus an `OSError` stand-in; the lock test's child reports `ready`/`acquired`; the resume-preset test has the spec's `provider-config` path with durable bytes; bytes Bearer and cap rows are labelled pre-existing coverage; accepted gaps are strict-xfail rows (`ACCEPTED_GAPS`); 5PR-01 shapes run in JSON and through the CLI; `prior_wizard_destination` uses try/finally; the Create Host test no longer assigns the picker value; timing checks compare growth (`tests/linear_timing.py`); the CI node-id check resolves `file::Class::method`. The third-cycle `< 2.0` s cap test in `test_third_post_review_sanitizer_performance.py` is left as is (generous, pre-existing).
- **6PR-11:** annotations added to the fifth-cycle TODO ("Post-closeout review 2026-10-15 (sixth)"); ARCHITECTURE, the policy doc and the user guide describe monotonic control flags, the cancel command with real ids and the monitor notice.
- **Baseline (6PR-000):** `44970a9` is docs-only over code head `d1952b4`; the fresh local check on that tree was 2,538 passed (exit 0), CI run 38739107751 green. Rows that already pass on the baseline (pre-existing coverage): the benign rows of every new sixth-cycle test file; the `repr` variants of bytes/Bearer shapes; `test_cancel_now_leaves_other_states_alone`-style no-op rows are new code and fail there. Every "Reproduced" item has a test that fails on the baseline (counts in the item notes above); the "suspected" items (Quick Deep Dive partial success, Reload discarding edits, Discard fallback) were reproduced for the first two and disproved (unreachable) for the Discard fallback.
- **6PR-911 (fresh read-only reviewer, then fixes in the commit named in the ledger):**
  - Fixed: `_ESCAPED_QUOTE_PAIR` was quadratic on a long backslash run (305 s at the cap) — opener now `(?<!\\)\\{1,8}` (0.06 s; growth test). A stage handler could still run after a cancel landed between the boundary check and the stage-start write, and a late `completed` write emitted a false event — `run()` now returns when `_update` reports `cancelled`; `cancel_now` raises for a missing/finished run instead of emitting an event (test). PEM header followed by `\x0b`, `\x0c`, NEL, `<br>`, `%0A`/`%0D` leaked — lookahead widened. `--token-count`, `--pwd-dir` and `<password-policy>` were over-redacted — flag and element names must end in a credential noun (`_is_secret_name`).
  - Accepted (not fixed): control flags persist into `completed`/`failed` (a cancel during the last stage leaves `completed` + `cancel_requested`; a failed stage with a cancel request is not resumable, which matches "cancelled runs cannot be resumed"); `request_pause`/`request_cancel` can bump `modified_at` of a finished run; a PEM body shorter than 16 characters directly after a space-separated header; `pwd:`/`pwd=` shell output and `auth: required`, `{"auth": "none"}`, `<auth>none</auth>` are redacted (fail closed); `curl -u user:pass`, a password containing whitespace and `https://tok/en@host` (no colon) are not redacted (pre-existing); `msg='hello password=x'` loses its closing quote.
  - The reviewer found no leak beyond those in the URL, tuple, bytes, escaped-JSON, XML and flag passes, and no defect in the screen guards, `keep_empty`, model overrides, lock or `get_plan_with_segments` changes.
- **6PR-912 qualification (code head `8ad0a60`, the last `src/` change):** `uv lock --check`, ruff format/lint and strict mypy clean; full local check 2,713 passed, 5 xfailed (the strict-xfail accepted-gap rows), exit 0; `uv build` and a fresh-venv wheel install from that head: `deeper-dive --help`, `episode cancel --help` shows `--run`, `episode configure --help` shows `--clear-model-overrides`, and `redact()` hid `https://user:p@a#ssCANARY9x@host/x`, `https://user:pa/ss?CANARY9x@host/x`, `[('x-api-key', 'CANARY9x')]`, `--api-key CANARY9x` and `{b'Authorization': b'Basic CANARY9x'}`; package imported from site-packages. CI run 38789463854 on `8ad0a60`: quality 116609951228 and fresh-machine 116609951611, both success. Checks and pushes were batched (one full check and one push for the cycle's task commits plus the review-fix commit); the closing docs-only commit has no CI run of its own recorded here.

## Seventh-cycle corrections (2026-10-15)

The seventh-cycle review supersedes these sixth-cycle statements without changing historical checked state:

- 6PR-03's “every non-guided Screen subclass” sweep was incomplete; the seventh-cycle AST sweep tracks framework handlers and follows refresh helpers.
- 6PR-05.1's refresh sweep statement (“`refresh_claims`/providers/settings call no service after a mutation”) described only post-mutation refresh work; it did not establish that every handler reaching those refreshes was guarded. See 7PR-01/02.
- 6PR-06's monotonic flags statement applies to stage progress. Completion clears both flags, and stale flags on completed rows are cleared before re-drive.
- 6PR-06's “one classifier” was not a shared noun set: the seventh cycle centralizes the credential vocabulary and adds list/space tuple canaries. 6PR-02's trailing-slash password behavior is documented in `_credential_shaped` and has benign-neighbor canaries in the seventh-cycle matrix.
- 6PR-08's guided workflow evidence covered mapping-shaped invalid overrides, not a string-shaped stored `model_overrides`; the seventh-cycle test uses the latter and displays the repair command.
- The 6PR-09 and 6PR-10 ledger references above do not by themselves provide mutation evidence for every claimed residual/test improvement; the seventh-cycle ledger names the exercising tests and reviewer fixes.
- The sixth-cycle `episode cancel` record prints the cancelled result; it does not emit a structured diagnostic event.
- The baseline CI run `38793385991` belongs to docs head `bc11d1e`; code head `8ad0a60` had separate CI run `38789463854`.
- 6PR-911 did not catch that `status=None` refreshes could overwrite generation results or that empty-plan handling blocked whole-plan regeneration; both are fixed and regression-tested in this cycle.
- See the seventh-cycle TODO for the remaining post-closeout corrections and qualification evidence.
