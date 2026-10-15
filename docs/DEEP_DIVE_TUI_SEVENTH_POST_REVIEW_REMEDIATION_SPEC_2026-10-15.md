# Deeper Dive TUI — Seventh Post-Review Remediation Specification

**Created:** 2026-10-15 (America/Los_Angeles)  
**Status:** Not started  
**Reviewed `master` baseline:** `bc11d1e` (sixth cycle closed; code head `8ad0a60`; line references below are valid against `bc11d1e`)  
**Companion authoritative implementation checklist:** `docs/DEEP_DIVE_TUI_SEVENTH_POST_REVIEW_REMEDIATION_TODO_2026-10-15.md`  
**Predecessor (historical, do not rewrite checked state):** `docs/DEEP_DIVE_TUI_SIXTH_POST_REVIEW_REMEDIATION_TODO_2026-10-15.md` and its spec  
**CI at baseline:** run 38793385991 on `bc11d1e` green. Run 38789463854 on `8ad0a60` green (quality 116609951228, fresh-machine 116609951611). Full local check on the `8ad0a60` tree: 2,713 passed, 5 xfailed.

## 1. Executive summary

Three independent reviewers carried out a read-only review of the completed sixth post-review cycle (every box ticked). They traced production code without the implementer's conclusions, reran the targeted tests (all pass), mutation-checked the new tests against the baseline source, ran about 600 repeated-prefix inputs through the sanitizer at the 262,144-character cap (all linear), and wrote throwaway reproducers.

The core of the sixth cycle holds up:
- Run-control flags are monotonic, a cancelled run stays cancelled, `episode cancel` runs no stage, and a late cancel starts no handler.
- The credential-URL rewrite redacts every shape it listed, stays linear, and keeps benign text intact.
- Empty stored values, string and `null` model overrides, the dangling-symlink lock change and the ledger's SHAs, CI ids and test count are correct.

The review nevertheless found that the legacy-screen sweep still missed the generation monitor (so the guard claim is false), several credential shapes still leak, and a few stored-data and process claims overstate the work.

| ID | Priority | Status | Topic | Main production surface |
| --- | --- | --- | --- | --- |
| 7PR-01 | High | Reproduced | Generation monitor actions and refreshes crash the app on a database error; Claim Inspector reports a successful repair as failed; Providers/Settings refresh after a successful save is unguarded | `generation_monitor.py`, `claim_inspector_screen.py`, `providers_screen.py`, `settings_screen.py` |
| 7PR-02 | Medium | Reproduced (blind spots) | The guard sweep exempted the monitor on a false reason and cannot see most entry points | `tests/test_sixth_post_review_legacy_crashes.py` |
| 7PR-03 | High | Reproduced | Credential leaks: password ending in `/`; header lists written with `[` or spaces; `--apikey`/`--pass`/`--passphrase` flags; `DB_PASS=`/`pass=`/`passphrase=`/`credentials=`/`sessionid=` assignments; tail of an escaped-quote secret | `diagnostics.py` |
| 7PR-04 | Medium | Reproduced / suspected | Stored-shape robustness: guided wizard hides the repair command for a string `model_overrides`; frozen episodes cannot be repaired; other stored `null` fields raise `TypeError`; legacy setup screen shows `<project_id>`; project wizard may keep "(not set)" | `guided_episode_form.py`, `episode_config.py`, `episode_setup_screen.py`, `guided_new_deep_dive.py`, `episode_library_screen.py` |
| 7PR-05 | Low | Reproduced | A plan with zero segments can be approved; Save/Regenerate Segment show raw errors | `episode_plan_screen.py`, `episode_planner.py` |
| 7PR-06 | Low | Source-verified / suspected | Run-control residuals: `episode cancel` event goes nowhere; `_set_flag` can touch a finished run; flags persist into `completed`; dangling symlink as a parent component; policy-doc placement | `pipeline.py`, `cli.py`, `run_repositories.py`, `user_config.py`, `docs/` |
| 7PR-07 | Medium (quality) | — | Sixth-cycle test weaknesses and ledger inaccuracies | `tests/`, sixth-cycle TODO |
| 7PR-08 | Process | — | Reconcile the sixth-cycle TODO (ticked boxes that were not true); re-qualify at the exact head | sixth-cycle TODO, docs |

"Reproduced" means a reviewer demonstrated the failure with a throwaway script (not committed; rewrite as permanent regression tests). "Suspected" means the first step is a deterministic reproducer that fails on the baseline, or a justified N/A with evidence.

## 2. Governing execution contract

Everything in the sixth-cycle contract (spec §2) still applies: work on current `master`; one task per commit with the task ID; no `Co-Authored-By` trailers; push only after `./scripts/check.sh` exits 0 with an `N passed` line; exact-head CI is part of done; test first at the highest practical boundary; sweep siblings; review fixes are tested, swept and mutation-checked; any `src/` change after final qualification re-opens it; a deviation is not a tick; discriminating rows only; accepted sanitizer gaps are strict-xfail rows. In addition:

- **A guard claim is checked by a test that can fail.** The sixth cycle ticked "every legacy action guarded" while its own exemption list excused four unguarded monitor actions with a reason nobody checked. Every exemption names a reason, and a test verifies the reason (see 7PR-02). A sweep that cannot see a class of entry points is not evidence for that class.
- **"Shared" means one definition.** A box that says a rule is shared by several passes is ticked only if a test or the code shows a single definition feeding them. If two sets must stay separate, say so in the box, not in a later note.
- **Ledger rows cite the test that exercises the fix.** A row whose mutation column names a test that does not touch the fix, or says "n/a" under a box that requires a mutation, is corrected in the same commit that notices it.
- **Review fixes** get the same treatment as task fixes, and the independent review of this cycle covers the sanitizer with a mixed-pass timing sweep and the screens with a pilot-driven fault injection of every entry point.

## 3. 7PR-01 — Legacy screens that still crash or mislabel

### Defect
- `GenerationMonitorScreen` (`generation_monitor.py:222-282`): `action_pause`, `action_resume`, `action_cancel` and `action_diagnostics` call `self._run()` before their `try`. `_run()` runs `controller.snapshot()`, which reads the database, so a locked database raises out of the handler and ends the app. The `refresh_monitor(...)` that follows a successful pause, resume or cancel is also outside the `try`: the request is already durable and the app dies. `action_resume` then never reaches `start_background_generation`. `_background_run` (`:292-300`) ends with an unguarded `self.refresh_monitor()` inside an asyncio task. The sixth cycle's `_REVIEWED` exempted these four actions as "except Exception with user_status", which is true only of the controller call.
- `ClaimInspectorScreen.action_repair` (`claim_inspector_screen.py:167-174`) runs `controller.repair`, then `refresh_claims()`; a failing refresh produces "Repair failed: …" although the repair committed (the same defect class as 6PR-05.1).
- `ProvidersScreen.action_save` and `action_confirm_remove` (`providers_screen.py:211`, `:239`) call `refresh_providers` after the config write; a config-read `OSError` escapes the handler. `SettingsScreen.refresh_settings` is probably the same (verify).

### Required behavior
1. Guard `_run()` in every monitor action (put it inside the guarded region or wrap the actions with `report_service_errors`), and keep the existing `user_status` mapping for controller errors. A failing refresh after a durable pause/resume/cancel reports "Pause requested … (the screen could not refresh: …)". After a successful resume, background generation still starts.
2. Guard the `refresh_monitor()` at the end of `_background_run` so the asyncio task cannot die on a refresh error; the generation result is reported first. Note `refresh_monitor(status=None)` treats `None` as "no change", so do not apply `tolerate_refresh_errors` blindly (its default status is `"Ready"`): either extend the decorator to accept `None` or guard locally.
3. `action_repair`: the refresh failure keeps "Turn repaired" plus the suffix. Same for providers `action_save`/`action_confirm_remove`, and settings if reproduced.
4. Sweep every legacy action and mount for "service call, then unguarded refresh" mechanically (extend 7PR-02's test to check it) and record the result.

### Acceptance
Pilot tests with a fake raising `sqlite3.OperationalError`/`OSError`, each failing on the baseline: monitor pause/resume/cancel/diagnostics with a failing snapshot; pause succeeds then refresh fails (status keeps success text, app alive, resume still starts generation); claim repair succeeds then refresh fails; providers save succeeds then the config read fails.

## 4. 7PR-02 — Guard sweep blind spots

### Defect
`tests/test_sixth_post_review_legacy_crashes.py` inspects only `action_*`, `on_mount` and `on_screen_resume`; skips `on_button_pressed`, `on_input_changed`, `on_input_submitted`, `on_select_changed` and `key_*`; detects service use only by the substrings "service", "controller", "repository" (a handler that opens `Database(...)`, does file I/O or calls `provider_controller`/`composition` is invisible); treats a class as a screen only if a base's source text contains "Screen" (an intermediate base would be missed); and never checks `_REVIEWED` reasons or flags stale entries.

### Required behavior
1. Inspect every handler a user or the framework can trigger: `action_*`, `on_*`, `key_*`, `watch_*`, plus `refresh_*` reached from them (transitively through unguarded `self.` helpers).
2. Detect service use by name sets that include `Database`, `composition`, `provider`, `open(`, `Path(`, `read_text`, `write_text` and `json.load`, or invert the rule: every handler that is not on an explicit pure-UI allowlist must be guarded.
3. Resolve screen classes through the AST class hierarchy (a class is a screen if any ancestor in the package is).
4. `_REVIEWED` entries carry a reason code that the test checks: `own-try` (the whole body, including `_run()`/refresh calls, is inside a `try` catching the service errors), `pure-ui`, `json-config` (catches the config errors). The test fails on an entry whose method no longer exists or whose reason code does not hold.

### Acceptance
The test fails on the baseline (it must report the four monitor actions and the claim/providers refreshes) and has a self-test that strips a guard and an exemption reason.

## 5. 7PR-03 — Credential leaks

### Defect (all confirmed with `redact()`)
- **Password ending in `/`:** `https://user:p/CANARY9x/@host`, `redis://:p/C/@host`, `https://user:pC/@host/x` come back unchanged. `_credential_shaped` (`diagnostics.py:139`) rejects any userinfo ending in `/` to protect `/@scope` path segments. Base64-style passwords ending in `/` are realistic.
- **Header lists written as lists or with spaces:** `[['x-api-key', 'C']]` and `[ 'x-api-key' , 'C' ]` are unchanged because `_TUPLE_PAIR` (`diagnostics.py:73-76`) requires a literal `(` before the key. JSON-decoded header lists are lists of lists.
- **Flag names:** `--apikey C`, `--accesstoken`, `--clientsecret`, `--privatekey` (one word), `--pass`, `--passphrase`, `--credentials`, `--key`, `-p` leak because `_is_secret_name` (`:441-450`) needs the last word in `_SECRET_LAST_WORDS`.
- **Assignments:** `DB_PASS=C`, `pass=C`, `passphrase=C`, `credentials=C`, `sessionid=C` leak: the assignment regex (`:57-59`) has its own keyword list and `_SENSITIVE_URL_KEYS` is a separate set, so the sixth cycle's "one shared set" box is false.
- **Escaped-quote tail:** `{\"api_key\": \"a\\\"C\"}` becomes `\"[REDACTED]\"C\"`: the value ends at the first inner escaped quote.

### Required behavior
1. Decide the trailing-`/` precedence: accept a trailing `/` when the text before the colon has no `/` and no `.` (a host-only prefix such as `user` or empty), or keep rejecting it and record the exact shape class as an accepted strict-xfail row with a docstring note. Whatever is chosen, `/@scope`, `repo/@v1` and `host:8080/@x` stay benign (tests both ways).
2. `_TUPLE_PAIR` accepts `(` or `[`, optional whitespace and an optional `b` prefix on both elements; add the list-of-lists, spaced and bytes variants.
3. One credential-noun set. Define it once (single words: `token`, `secret`, `password`, `passwd`, `pwd`, `pass`, `passphrase`, `auth`, `authorization`, `cookie`, `credential(s)`, `session`, `sessionid`, `apikey`, `accesstoken`, `clientsecret`, `privatekey`; pairs: `api key`, `access token`, …) and build the assignment keyword alternation, `_is_secret_key`, `_is_secret_name`, the URL-query check and the flag/element rules from it. Keep a documented, separate set only for query-only generic names (`key`, `code`, `sig`, `sid`) and say so in the box.
4. Flags: a flag is sensitive when its name (dashes stripped) is a credential noun alone or ends in one (`--db-pass`, `--apikey`); keep `--token-count`, `--pwd-dir`, `--max-tokens` benign. `-p` stays benign unless followed by a credential-looking value (decide; default: leave `-p` and record it).
5. Escaped-quote values: end at the matching escaped quote that is not itself preceded by an odd number of backslashes, or fail closed to the end of the line. Keep the 2,048-character bound and the `(?<!\\)` anchor.
6. Every shape becomes a canary row, with its JSON and `repr` embedding where meaningful, plus benign rows for the nearby ordinary text (`password_policy=strict`, `passenger=3`, `--passenger-count 2`, `compass=north`).

### Acceptance
Each shape fails on the baseline and passes now; timing is checked with a mixed-pass sweep (no growth worse than linear for any pair of passes) and the worst case at the cap is recorded.

## 6. 7PR-04 — Stored-shape robustness

1. **Guided repair message.** `_load_episode_form` (`guided_episode_form.py:84-96`) swallows `(KeyError, ValueError)`, so a stored `model_overrides` string leaves `_loaded_episode_config` as `None` and Save says "Episode settings are not loaded; reopen the episode before saving." Reopening cannot fix it. Surface `InvalidModelOverrides` on load: show `describe(project_id, episode_id)` in `#guided-episode-validation` and the status, and keep other load failures as they are. Test with the string shape (the sixth cycle's pilot covered only the dict shape).
2. **Frozen episodes.** `--clear-model-overrides` goes through `edit()`, which raises `EpisodeFrozenError` for a non-draft episode; Library Duplicate on such an episode fails with a message that points at the same CLI command. Reproduce first. Decide: a documented repair that works for frozen episodes (for example `duplicate` loads with `drop_invalid_model_overrides=True` and the message says so), or an N/A with the user-facing instruction "duplicate it".
3. **Other stored `null`/odd shapes.** `configuration_from_record` (`episode_config.py` around `:258`) does `dict(payload.get("source_overrides", {}))`, `dict(…research_overrides…)`, `tuple(payload.get("must_cover", ()))`, `tuple(…avoid_topics…)`. A stored `null` raises `TypeError`. Treat `null` as empty, and raise one typed, field-naming `EpisodeConfigurationError` for any other non-conforming shape. Test each field.
4. **Legacy setup placeholder.** The setup screen shows the override-repair message without ids (`describe()` is used only in the CLI and guided paths). Use `describe` there too.
5. **Project wizard stale state.** `_project_audience_unset` and the "(not set)" option persist on a reused `GuidedProjectWizard` instance; `_load_project_form` returns early when `project_id is None`. Reproduce (find whether the screen is re-instantiated); fix by resetting both when no project is loaded, or N/A with evidence.

## 7. 7PR-05 — Empty plan approval

After 6PR-05's zero-segment fix, `action_approve_generate` on a plan with no segments says "Plan approved; generation remains explicitly gated"; `action_save_segment` shows `invalid literal for int() with base 10: ''`; `action_regenerate_segment` shows "Segment not regenerated: 0".

Required: `_plan_context` (or each action) refuses an empty plan with "The stored plan has no segments; regenerate the plan"; `approve_plan` rejects an empty plan with a typed error at the service level (so the CLI and guided paths agree); Save/Regenerate Segment validate the selected segment before parsing inputs. Tests at the service level and by pilot with a real stored plan whose segment rows were deleted.

## 8. 7PR-06 — Run-control and lock residuals

1. **Cancel event.** `pipeline.cancel_now` emits "cancelled" to a `ProgressSink` the CLI never supplies, so nobody sees it. Either log it through the structured diagnostic log or drop the claim from the docs; the spec asked for "the same event". Decide and test.
2. **`_set_flag` on a finished run.** `request_pause`/`request_cancel` bump `modified_at` of a completed/failed/cancelled run. Guard the statement with `AND state IN ('pending','running','paused')` (return whether it applied) so a late request is a no-op, and make `pipeline.request_*` raise as they already do for terminal states.
3. **Flags persisting into `completed`.** The sixth cycle documents that a cancel/pause requested during the last stage leaves `completed` with the flag set, and `run(force_from=…)` on such a run would turn it `cancelled`. Decide: clear both flags when a run reaches `completed` (a terminal transition owns that decision, as the sixth spec said), or keep and test that re-driving a completed run ignores stale flags. Record the decision in the policy doc.
4. **Dangling symlink as a parent.** The lock check only inspects the final path component. Resolve with `strict=False` and compare: if any existing component of `self.path` is a symlink whose target does not exist (or the resolved parent differs from the lexical parent and does not exist), refuse before `mkdir`. Reproduce first; N/A with evidence if `resolve()` cannot create anything outside the intended tree.
5. **Docs.** Move the "Control flags are monotonic (6PR-01)" bullet in `docs/GENERATION_RUN_SELECTION_POLICY.md` under the selection rules, not after the qualification paragraph; reword the user-guide sentence about the monitor notice ("shown when the stopping run is not the one displayed").

## 9. 7PR-07 — Test quality

1. `tests/test_fifth_post_review_config_lock_processes.py:62-64`: reading `process.stderr` in the assert message can block forever if the child is alive when the 60-second ready wait expires. Kill the child, then read stderr (or use `communicate(timeout=…)`).
2. `tests/linear_timing.py`: the pass condition `max(8 * small, 0.5) + 1.0` passes any run under 1.5 s. Measure at three sizes (1×, 2×, 4×) and require the 4× time to be at most about 6× the 1× time once the 1× time exceeds a noise floor, or count regex steps with a deterministic probe; keep a generous absolute ceiling only as a hang guard. Add a self-test with a deliberately quadratic function.
3. `tests/test_fifth_post_review_residuals.py` Create Host test reads the private `picker._options`. Find the target by the picker's public `value`/prompt and the option labels (`Select` has no public option list: use the host list from the repository and press keys until `_loaded_host_id` matches, bounded).
4. The monitor/claim/providers tests from 7PR-01 inject faults through public seams, not by patching private methods where a seam exists.
5. Ledger corrections in the sixth-cycle TODO (done in 7PR-08): the 6PR-09 mutation column names the residuals tests; 6PR-10/6PR-11 "n/a" is explained under the box that requires a mutation.

## 10. 7PR-08 — Process and documentation reconciliation

1. **Sixth-cycle TODO.** Add dated annotations and ledger corrections only; do not uncheck anything.
   - 6PR-03 "every legacy action guarded" and 6PR-05.1 "sweep every legacy action": false for the monitor, Claim Inspector and Providers (point to 7PR-01/02).
   - 6PR-06 "one sensitive-key set": false (7PR-03); bytes/tuple coverage incomplete (list/space forms).
   - 6PR-02: trailing-`/` password not recorded as an accepted gap (7PR-03).
   - 6PR-08 guided-repair box true only for the dict shape (7PR-04).
   - 6PR-09 and 6PR-10 ledger rows (see 7PR-07.5); the 6PR-912 note that the closing commit has no CI run: run 38793385991 on `bc11d1e` is green.
   - 6PR-911: the review missed the monitor, the claim mislabel and the shared-set claim.
   - Add a "Post-closeout review 2026-10-15 (seventh)" note pointing to this spec.
2. **Policy doc and user guide** match 7PR-06.
3. **Final qualification at the exact head**, after the last `src/` change:
   - `uv lock --check`
   - ruff format and lint
   - strict mypy
   - full pytest count
   - `uv build`
   - fresh-venv wheel smoke, including one 7PR-03 redaction check (`--apikey C`, `[['x-api-key','C']]`) and `deeper-dive episode cancel --help`
   - green CI on both jobs, with run and job IDs

   If any commit touches `src/` after this step, repeat the whole step.
