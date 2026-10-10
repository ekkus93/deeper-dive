# Second Post-Review: Persistence, Readiness and Episode Lifecycle

**Date:** 2026-10-10  
**Authority:** `docs/DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_SPEC_2026-10-09.md` and its TODO  
**Status:** Partial implementation and qualification; the TODO remains the final completion authority.

## Configuration persistence and concurrency

`UserConfigStore.save()` revalidates mutated Pydantic configuration and serializes a complete JSON candidate before publication. The store protects load/save with a process-local reentrant lock plus POSIX advisory file lock where supported, checks the persisted revision digest against the caller's loaded revision, and reports stale writers as conflicts requiring explicit reload/retry. `ProviderController` validates candidates before building provider runtimes and publishing changes; the store validates again before writing. A conflict is never silently resolved by last-write-wins.

The writer uses a unique owner-only same-directory temporary file, flushes and fsyncs its bytes, finalizes permissions, atomically replaces the destination, and fsyncs the containing directory where supported. Pre-replace errors leave the prior configuration bytes intact and clean owned temp files where the OS permits. Post-replace directory fsync errors mean publication happened but crash durability is uncertain; the candidate revision remains aligned with the new bytes. Cleanup failure never masks the original write error. The supported boundary assumes a trusted, owned config directory, and cannot defend against full same-UID compromise. Destination and lock symlink checks provide defense in depth on supported POSIX systems.

## First-run readiness lifecycle

A `FirstRunReadinessCoordinator` runs provider/system probes away from Textual's UI thread with a configurable bound (`max_workers=2` by default) and no request queue. Identical pending fingerprints coalesce callbacks; a new fingerprint supersedes old status but not an uninterruptible in-flight provider call. Supersession immediately cancels obsolete timers, and a request is responsible for releasing its reserved worker slot if it loses the generation race before starting. Completion, error and timeout publication are guarded by generation/fingerprint and closed-state checks. A timed-out probe cannot publish a late Ready result. Closing the coordinator cancels owned timers and suppresses late callbacks, but does **not** kill arbitrary blocked Python threads.

Actual socket/client transport deadlines in each provider adapter must be audited separately; UI deadlines alone are not proof that network I/O terminates. UI and installed-wheel readiness matrices remain open in the TODO.

## Episode plan and historical artifact identity

`EpisodeConfigurationService.edit()` returns without mutation for a semantically identical persisted configuration. Meaningful draft changes use the transactional `EpisodeConfigurationRepository.update()` path, compare the expected `config_json` and current draft state, and invalidate only that episode's replaceable plan/segments. Generation-started or non-draft edits are prohibited rather than silently demoting historical episodes. Planner replacement checks the episode config revision under the same database transaction to prevent stale plans being committed after an edit. Completed runs, transcript/audio exports and plan identities must remain stable on a no-op; pending generation must not accept a changed configuration. Cross-surface lifecycle, revision and run-state qualification is still in progress.

## Regression and qualification evidence

`tests/test_second_post_review_config_durability.py` and `tests/test_second_post_review_config_failure_matrix.py` exercise revision CAS, write failure injection, symlink defenses and restart-readable JSON. `tests/test_second_post_review_readiness_budget.py` exercises coalescing, worker bounds, timeouts, closure and supersession races. `tests/test_second_post_review_episode_lifecycle.py` and `tests/test_second_post_review_acceptance_matrix.py` exercise plan invalidation, stale edits, multi-project complete/pending runs and export identity via the shared fake-provider fixture in `tests/conftest.py`.

- Configuration and lifecycle qualification: [CI #2491](https://github.com/ekkus93/deeper-dive/actions/runs/38069863354), exact `935124fb0c4ccc259f38e2001b50a9a10367784c`, 1,214 tests.
- Worker supersession qualification: [CI #2494](https://github.com/ekkus93/deeper-dive/actions/runs/38071463889), exact `eff4eb7962581a7567f0bf93e9895aca134176f3`, 1,216 tests plus fresh-machine pass.

These are **partial** qualification milestones. Check the authoritative TODO before claiming full second post-review remediation complete.
