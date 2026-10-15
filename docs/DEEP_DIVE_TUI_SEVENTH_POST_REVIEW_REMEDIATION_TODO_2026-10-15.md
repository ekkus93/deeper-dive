# Deeper Dive TUI — Seventh Post-Review Remediation TODO

**Created:** 2026-10-15 (America/Los_Angeles)  
**Status:** Implementation and local qualification complete; mutation and exhaustive review deviations recorded
**Authority:** `docs/DEEP_DIVE_TUI_SEVENTH_POST_REVIEW_REMEDIATION_SPEC_2026-10-15.md`  
**Reviewed baseline:** `bc11d1e` (CI run 38793385991 green; code head `8ad0a60`, CI run 38789463854 green; local 2,713 passed, 5 xfailed on the `8ad0a60` tree)  
**Predecessor historical checklist:** `docs/DEEP_DIVE_TUI_SIXTH_POST_REVIEW_REMEDIATION_TODO_2026-10-15.md`

This is the only completion checklist for the seventh post-review cycle. No item is prechecked. A checked item must identify:

- the production behavior that changed;
- a deterministic test that failed before the fix;
- the commit SHA;
- a green exact-head CI run.

If a reproducer disproves a finding, keep the task visible and record a justified N/A with exact evidence.

## Execution rules

- At every run start and after every `master` push, reload this TODO and the spec, inspect the exact head and its CI, and avoid duplicating landed work.
- One task per commit, with the task ID in the message and no `Co-Authored-By` trailers. Push only after `./scripts/check.sh` exits 0 with an `N passed` line.
- **CI is part of done.** `check.sh` does not run `fresh-machine`. A commit that renames, moves or deletes a test file updates `.github/workflows/ci.yml` in the same commit. Record the green run ID before ticking.
- **Test first**, at the highest practical boundary: pilot tests for screens (fault injected through a public seam), service/DB tests for storage, matrices for the sanitizer. Any test that seeds state, calls `action_*` directly, assigns `widget.value` or patches a private method records why in a comment.
- **A deviation is not a tick.** A subtask done differently, or not done, stays unchecked and is marked `N/A (deviation):` with the reason, or is reworded in the same commit.
- **A guard claim is checked by a test that can fail**; exemptions carry a verified reason code. **"Shared" means one definition.** Ledger rows cite the test that exercises the fix.
- **Discriminating rows only:** rows that already pass on the baseline are labelled "pre-existing coverage". Accepted sanitizer gaps are strict-xfail rows in the matrix file as well as the ledger.
- **Sweep siblings:** every fix greps for the same pattern elsewhere and records the result in the item's evidence line.
- **Review fixes** are tested, swept and mutation-checked like task fixes, and the ledger names their SHA.
- **Any `src/` change after 7PR-912 re-opens 7PR-912.**
- Do not change checked state in the sixth-cycle TODO; 7PR-08 adds annotations and ledger corrections only.

## 7PR-000 — Baseline

- [ ] Record the baseline head (`bc11d1e`), the full local check count on the `8ad0a60` tree (2,713 passed, 5 xfailed) and CI run 38793385991.
- [ ] Every "Reproduced" item has a committed regression test that fails on the baseline. Every "suspected" item has a deterministic reproducer or a justified N/A. List rows that already pass on the baseline.

## 7PR-100 — Crashes, leaks, stored data

### 7PR-01 — Legacy screens that still crash or mislabel
- [ ] Pilot regressions with a fake raising `sqlite3.OperationalError` (each fails on the baseline): monitor pause, resume, cancel and diagnostics with a failing snapshot; app alive, status shown.
- [ ] Monitor actions guard `_run()`; a failing `refresh_monitor` after a durable pause/resume/cancel keeps the success text plus a could-not-refresh suffix; after a successful resume background generation still starts. Test the decorator/None-status interaction (`refresh_monitor(status=None)` means "no change").
- [ ] `_background_run` cannot die on a refresh error (the generation result is reported first). Test.
- [ ] `ClaimInspectorScreen.action_repair`: a failing refresh after a committed repair reports "Turn repaired" with the suffix. Test.
- [ ] Providers `action_save` / `action_confirm_remove` (and Settings `refresh_settings` if reproduced): a failing refresh after a successful write reports success with the suffix. Tests.
- [ ] Sweep every legacy action and mount for "service call, then unguarded refresh" (mechanical check in 7PR-02) and record the result.

### 7PR-02 — Guard sweep blind spots
- [ ] The sweep inspects every user- or framework-triggered handler (`action_*`, `on_*`, `key_*`, `watch_*`) and the `refresh_*` reached from them transitively.
- [ ] Service use is detected by an extended name set (`Database`, `composition`, `provider`, file I/O, JSON loads) or inverted to an explicit pure-UI allowlist.
- [ ] Screen classes are resolved through the AST class hierarchy, not by the text "Screen" in a base.
- [ ] `_REVIEWED` entries carry a verified reason code (`own-try` checks the whole body incl. `_run()`/refresh calls; `pure-ui`; `json-config`); stale entries and failed reasons fail the test.
- [ ] The test fails on the baseline (reports the four monitor actions and the claim/providers refreshes) and has self-tests (strip a guard; strip a reason).

### 7PR-03 — Credential leaks
- [ ] Canary rows that fail on the baseline, each with JSON/`repr` embedding where meaningful:
  - `https://user:p/CANARY9x/@host`, `redis://:p/C/@host`, `https://user:pC/@host/x`
  - `[['x-api-key', 'C']]`, `[ 'x-api-key' , 'C' ]`, bytes list-of-lists variant
  - `--apikey C`, `--accesstoken C`, `--clientsecret C`, `--privatekey C`, `--pass C`, `--passphrase C`, `--credentials C`, `--db-pass C`
  - `DB_PASS=C`, `pass=C`, `passphrase=C`, `credentials=C`, `sessionid=C`
  - `{\"api_key\": \"a\\\"C\"}` (escaped inner quote)
- [ ] Trailing-`/` password decided and documented in the `_userinfo_end` docstring; `/@scope`, `repo/@v1`, `host:8080/@x` stay benign (both directions tested); any remaining shape is a named strict-xfail row.
- [ ] `_TUPLE_PAIR` accepts `(` or `[`, whitespace and `b` prefixes on both elements.
- [ ] One credential-noun set feeds the assignment alternation, `_is_secret_key`, `_is_secret_name`, the URL-query check and the flag/element rules; the separate query-only generic set (`key`, `code`, `sig`, `sid`) is documented in the box and the docstring. A test shows the passes agree (the same names are sensitive in assignment, mapping, flag and element form).
- [ ] Flag names: a credential noun alone or as last word (including one-word spellings) is sensitive; `--token-count`, `--pwd-dir`, `--max-tokens` stay benign; `-p` decision recorded.
- [ ] Escaped-quote values end at the matching unescaped-by-odd-backslash escaped quote or fail closed to end of line; the 2,048 bound and `(?<!\\)` anchor stay.
- [ ] Benign rows: `password_policy=strict`, `passenger=3`, `--passenger-count 2`, `compass=north`, the sixth-cycle benign rows unchanged.
- [ ] Mixed-pass timing sweep at the 262,144 cap (every pair of new passes, growth ratio) and the worst case recorded.

### 7PR-04 — Stored-shape robustness
- [ ] Guided episode form surfaces `InvalidModelOverrides` on load with the real repair command (string `model_overrides` shape); other load failures unchanged. Pilot test with the string shape, fails on the baseline.
- [ ] Frozen-episode repair: reproduce (`edit()` raises `EpisodeFrozenError`; Library Duplicate fails) and then either make Duplicate load with `drop_invalid_model_overrides=True` and say so, or record an N/A with the user-facing instruction. Test.
- [ ] Stored `null` for `source_overrides`, `research_overrides`, `must_cover`, `avoid_topics` loads as empty; any other non-conforming shape raises one typed, field-naming `EpisodeConfigurationError`. One test per field; fails on the baseline.
- [ ] The legacy setup screen shows the repair command with the real project and episode ids.
- [ ] Project wizard: reproduce whether `_project_audience_unset` / "(not set)" persist across loads (reused instance); reset both when no project is loaded, or N/A with evidence.

### 7PR-05 — Empty plan approval
- [ ] Service level: `approve_plan` rejects a plan with no segments with a typed error. Fails on the baseline.
- [ ] Plan screen: Approve, Save Segment and Regenerate Segment refuse an empty plan with "The stored plan has no segments; regenerate the plan" (no raw `int()`/`0` errors). Pilot test with a real stored plan whose segment rows were deleted.

## 7PR-200 — Residuals

### 7PR-06 — Run-control and lock residuals
- [ ] `episode cancel` event: recorded through the structured diagnostic log, or the docs stop claiming it; decision and test.
- [ ] `_set_flag` is a no-op for terminal runs (`AND state IN ('pending','running','paused')`, returns whether it applied); a late `request_*` does not bump `modified_at` of a finished run. Test fails on the baseline.
- [ ] Flags at `completed`: decide (clear on the terminal transition, or ignore stale flags when re-driving) and record in `docs/GENERATION_RUN_SELECTION_POLICY.md`; test `run(force_from=…)` on a completed run with a stale cancel flag.
- [ ] Dangling symlink as a parent component: reproduce; refuse before `mkdir`, or N/A with evidence.
- [ ] Policy-doc bullet moved under the selection rules; user-guide sentence reworded.

## 7PR-300 — Tests and process

### 7PR-07 — Test quality
- [ ] Lock-test child protocol cannot block on `stderr`: kill first, then read (or `communicate(timeout=…)`); a test of the helper with a child that never prints `ready`.
- [ ] `linear_timing` measures three sizes and fails a deliberately quadratic function (self-test); keeps a generous absolute hang guard.
- [ ] Create Host test no longer reads `picker._options` (public seam, bounded key presses until `_loaded_host_id` matches).
- [ ] The new monitor/claim/providers tests inject faults through public seams; private patches are justified in comments.

### 7PR-08 — Process and documentation reconciliation
- [ ] Sixth-cycle TODO annotations (no unchecking): 6PR-03 / 6PR-05.1 false sweep claims, 6PR-06 shared-set box and list/space tuple gap, 6PR-02 trailing-`/` password, 6PR-08 dict-only guided box, 6PR-09 / 6PR-10 ledger rows, run 38793385991 on `bc11d1e`, 6PR-911 missed items.
- [ ] Add a "Post-closeout review 2026-10-15 (seventh)" note in the sixth-cycle TODO pointing to this cycle.
- [ ] Policy doc, ARCHITECTURE and the user guide match 7PR-06.

## 7PR-900 — Review and qualification

### 7PR-911 — Independent review
- [ ] A fresh read-only reviewer with no prior conclusions traces every changed source path, fault-injects every screen entry point by pilot, and runs a mixed-pass timing sweep on the sanitizer. Every finding is fixed (with a test, a sweep and a mutation check) or recorded as accepted with a reason. Review-fix commits are named by SHA.

### 7PR-912 — Final qualification (after the last `src/` change)
- [ ] `uv lock --check`; ruff format and lint; strict mypy; full pytest count recorded at the exact head.
- [ ] `uv build`; fresh-venv wheel smoke at the exact head, including one 7PR-03 redaction check (`--apikey C`, `[['x-api-key','C']]`) and `deeper-dive episode cancel --help`.
- [x] Green exact-head CI on both jobs, with run and job IDs for source head `5c3f677`: run `38823465614`; `quality` job `116725302629`; `fresh-machine` job `116725302341`. The later documentation evidence commit is awaiting its own exact-head CI.
- [ ] Evidence ledger below complete. Every row's test fails with its fix reverted (Mutation column) and names the test that exercises the fix, including review fixes.

## Evidence ledger

| Item | Outcome | Commit(s) | Test file(s) | Mutation |
|---|---|---|---|---|
| 7PR-01 | Implemented; focused cases pass | `4a8f88d` | `test_generation_monitor.py`, `test_claim_inspector_screen.py`, `test_providers_tui.py`, `test_settings_screen.py` | N/A (deviation): systematic revert-and-fail mutations not run; do not tick mutation-required rows |
| 7PR-02 | Implemented scanner, inheritance and self-checks | `a8ee422` | `test_sixth_post_review_legacy_crashes.py` | N/A (deviation): systematic revert-and-fail mutations not run; do not tick mutation-required rows |
| 7PR-03 | Implemented; added irregular-case fix after full-suite discovery | `1a7d230`, `5c3f677` | `test_seventh_post_review_sanitizer.py`, `test_second_post_review_config_durability.py`, `test_recursive_redaction.py` | Focused regression cases pass; systematic source-revert mutations not run (deviation) |
| 7PR-04 | Implemented typed malformed stored-field handling and repair guidance | `14cef34` | `test_episode_config.py`, `test_episode_library_screen.py`, `test_guided_episode_wizard_part1.py` | N/A (deviation): systematic revert-and-fail mutations not run; do not tick mutation-required rows |
| 7PR-05 | Implemented service and screen guards for empty plans | `128ed0b` | `test_episode_planner.py`, `test_episode_plan_screen.py` | N/A (deviation): systematic revert-and-fail mutations not run; do not tick mutation-required rows |
| 7PR-06 | Implemented terminal run-control, lock and docs decisions | `b6ae4c2`, `18cec8b` | `test_pipeline_control_transitions.py`, `test_run_repositories.py`, `test_fifth_post_review_config_lock_processes.py` | N/A (deviation): systematic revert-and-fail mutations not run; do not tick mutation-required rows |
| 7PR-07 | Implemented timing/process helpers; stabilized asynchronous readiness tests | `dbd9453`, `8fca45b`, `23d97bf`, `930bdb3`, `18ce3a5`, `4dd736b`, `e00915b`, `cfa5a7f` | `test_linear_timing.py`, `test_fifth_post_review_config_lock_processes.py`, `test_fifth_post_review_residuals.py`, `test_guided_app.py`, `test_guided_first_run.py`, `test_post_review_first_run_research_parity.py` | Timing helper self-test passes; source-revert mutations not run (deviation) |
| 7PR-08 | Reconciled predecessor TODO and policy/user docs | `9a7970e`, `b6ae4c2` | Documentation review; run-control tests above | N/A (documentation-only) |
| 7PR-911 | Partial: prior independent review found two defects and a timing bound; exhaustive fresh trace of every changed source path remains unverified | `5c3f677` (review fix) | `test_generation_monitor.py`, `test_episode_plan_screen.py`, `test_seventh_post_review_sanitizer.py` | Review fixes tested; exhaustive reviewer mutation checks not completed (deviation) |

## Evidence notes

(Record baseline counts, sweep results, design decisions, deviations, accepted gaps and qualification evidence here.)

- Baseline already verified before edits: docs head `e58907e` over code head `8ad0a60`; cycle baseline CI run `38793385991` was green. The prior local baseline count is 2,713 passed and 5 xfailed.
- `-p` is intentionally benign because a one-letter option is ambiguous and commonly means a non-secret switch; long credential names such as `--pass` are redacted. The sanitizer docstring and `-p 3` benign row record this choice.
- Independent 7PR-911 review found and regression-tested two defects: statusless refresh failure overwrote the monitor's completed result, and the empty-plan guard also blocked whole-plan regeneration. Review timing on mixed passes at 262,144 characters: slowest pair assignment + percent-encoded URL, 0.3385 seconds best-of-three (0.3408, 0.3421, 0.3385 samples).
- Wheel smoke initially used `pip install --no-deps` and failed to import `pypdf`; the corrected smoke installs declared dependencies. A first corrected run exposed that structured nested header-pair objects were not redacted, so `redact([["x-api-key", "CANARY9x"]])` now redacts the value and has a regression test.
- Exact-head local qualification on `5c3f677`: `./scripts/check.sh` passed, 2,777 passed and 5 xfailed in 1,493.41 seconds; `uv lock --check`; `uv build`; fresh venv wheel install/import; `--apikey CANARY9x`, nested `[["x-api-key", "CANARY9x"]]`, and `deeper-dive episode cancel --help` smoke checks passed.
- The full mixed-pass sanitizer timing test passed at the 262,144-character cap; recorded worst pair remains assignment + percent-encoded URL at 0.3385 seconds best-of-three. `tests/test_linear_timing.py` verifies rejection of quadratic work.
- Push `5c3f677192bb90df8543e8a0d24fde24d3d221d0` triggered green CI run `38823465614`; `quality` job `116725302629` and `fresh-machine` job `116725302341` both passed. Documentation changes require a later exact-head run.
- Mutation/reversion checks required by the checklist were not performed systematically. The corresponding boxes remain unchecked. The 7PR-911 requirement for an independent exhaustive trace of every changed source path also remains open; the earlier independent review was narrower and found the two defects recorded above.
