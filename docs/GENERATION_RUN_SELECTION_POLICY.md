# Generation Run Selection Policy

Generation starts are routed through `GenerationStartService`, which is the shared readiness and duplicate-safety boundary for CLI and TUI generation surfaces.

## Selection rules

- If the selected episode already has an active run in `pending`, `running`, or `paused` state and that run is not cancel-requested, a new Generate action reuses that run.
- If the selected episode's latest run is terminal (`completed`, `failed`, or `cancelled`), a new Generate action creates a fresh `pending` run.
- If the latest active run has `cancel_requested=true`, a new Generate action creates a fresh `pending` run rather than reviving the cancelling run.
- Unknown persisted run states fail closed with an actionable error instead of creating another run.

## Surface contract

- CLI `episode generate` calls the shared start service before executing the pipeline.
- TUI Generate calls the same shared start service before navigating to the monitor.
- Status, control, resume, review, and export surfaces should operate on the selected episode's active/latest durable run identity rather than creating hidden replacement runs.

## Qualification expectations

Run-selection changes require tests for the service policy and for at least one CLI/TUI surface path. Behavior is complete only after exact-head CI, merge to `master`, TODO reconciliation, reload from `master`, and merged-master CI.
