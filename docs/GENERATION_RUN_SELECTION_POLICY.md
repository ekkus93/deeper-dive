# Generation Run Selection Policy

Generation starts are routed through `GenerationStartService`, which is the shared readiness and duplicate-safety boundary for CLI and TUI generation surfaces.

## Selection rules

- If the selected episode already has an active run in `pending`, `running`, or `paused` state and that run is not cancel-requested, a new Generate action reuses that run.
- If the selected episode's latest run is terminal (`completed`, `failed`, or `cancelled`), a new Generate action creates a fresh `pending` run.
- If any `pending` or `running` run has `cancel_requested=true`, a new Generate action is refused with "the previous run is still stopping" (`GenerationRunStillStopping`, a `ValueError`). Cancellation is honored only at a stage boundary, so that run keeps executing and a second run would share its episode-keyed state. Once the run reaches `cancelled` (or another terminal state), Generate creates a fresh `pending` run. The message names the blocking run and the exact command, `deeper-dive episode cancel <project_id> <episode_id> --run <run_id>`, which finishes stopping a run whose worker died (5PR-02). Without `--run`, `episode cancel` targets the oldest blocking cancel-requested run, then the latest run. It finalizes the cancel with one conditional write (`UPDATE … SET state='cancelled' WHERE state IN ('pending','running','paused')`) and runs no executor, so the command never executes a stage, even if a live worker writes concurrently (6PR-01); there is no worker liveness model, so run it only when the worker is gone or you accept the run being marked `cancelled` at once (a live worker stops at its next boundary). A `paused` run with a cancel request executes nothing and can never reach a boundary, so it does not block a new run. (Changed by FPR-06; earlier versions created the fresh run immediately.)
- The check looks at every run of the episode, not only the latest one.
- Unknown persisted run states fail closed with an actionable error instead of creating another run.
- Control flags are monotonic during stage progress. A terminal transition to `completed` clears both flags; before a completed run is re-driven, any stale flags from older records are cleared.

## Surface contract

- CLI `episode generate` calls the shared start service before executing the pipeline.
- TUI Generate calls the same shared start service before navigating to the monitor.
- Status, control, resume, review, and export surfaces should operate on the selected episode's active/latest durable run identity rather than creating hidden replacement runs.

## Qualification expectations

Run-selection changes require tests for the service policy and for at least one CLI/TUI surface path. Behavior is complete only after exact-head CI, merge to `master`, TODO reconciliation, reload from `master`, and merged-master CI.
