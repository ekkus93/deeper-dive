# Generation Run Selection Policy

Generation starts are routed through `GenerationStartService`, which is the shared readiness and duplicate-safety boundary for CLI and TUI generation surfaces.

## Selection rules

- If the selected episode already has an active run in `pending`, `running`, or `paused` state and that run is not cancel-requested, a new Generate action reuses that run.
- If the selected episode's latest run is terminal (`completed`, `failed`, or `cancelled`), a new Generate action creates a fresh `pending` run.
- If any active run (`pending`, `running`, or `paused`) has `cancel_requested=true`, a new Generate action is refused with "the previous run is still stopping" (`GenerationRunStillStopping`, a `ValueError`). Cancellation is honored only at a stage boundary, so that run keeps executing and a second run would share its episode-keyed state. Once the run reaches `cancelled` (or another terminal state), Generate creates a fresh `pending` run. (Changed by FPR-06; earlier versions created the fresh run immediately.)
- The check looks at every run of the episode, not only the latest one.
- Unknown persisted run states fail closed with an actionable error instead of creating another run.

## Surface contract

- CLI `episode generate` calls the shared start service before executing the pipeline.
- TUI Generate calls the same shared start service before navigating to the monitor.
- Status, control, resume, review, and export surfaces should operate on the selected episode's active/latest durable run identity rather than creating hidden replacement runs.

## Qualification expectations

Run-selection changes require tests for the service policy and for at least one CLI/TUI surface path. Behavior is complete only after exact-head CI, merge to `master`, TODO reconciliation, reload from `master`, and merged-master CI.
