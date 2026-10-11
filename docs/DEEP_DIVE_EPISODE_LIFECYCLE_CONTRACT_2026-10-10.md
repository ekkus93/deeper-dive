# Deeper Dive episode lifecycle contract — SPR-07

**Evidence baseline:** `366ec6ffa84cb6cf047852b298334c35e9bdf54e`, [exact-head CI #2548](https://github.com/ekkus93/deeper-dive/actions/runs/38117450369), quality job `114405081437`, fresh-machine job `114405081548` (both passed); later exact-head [CI #38118100638](https://github.com/ekkus93/deeper-dive/actions/runs/38118100638) for `9c3c91459558b40283baa44225cfae395813b3ea` passed both jobs.

## State and edit policy

The episode *row* state and latest generation *run* state have different purposes. `EpisodeLibraryController` and guided Home display the latest run state when a run exists; a completed/paused/failed run does not necessarily rewrite `episodes.state`. The authoritative edit guard checks both.

- **Draft:** `EpisodeConfigurationService.edit` validates same-project hosts and compares full semantic snapshots. Identical snapshots (including differently ordered mappings) return the existing record unchanged; plan/segment IDs survive. A changed snapshot invalidates only the selected draft episode's plan, in the same SQLite transaction as the episode and ordered-host update.
- **Planned, running, paused, failed, completed episode rows:** Changed configuration is forbidden; the service raises a create-new-episode guidance error. Identical submissions are harmless no-ops. In addition, a durable generation run, conversation state or turn blocks changed configuration *even if the episode row still says draft*. `EpisodeConfigurationRepository.update` enforces both constraints in an immediate transaction, not merely in the UI.
- **Historical identity:** No-op or forbidden changes preserve generation run IDs/state, current plan and segment IDs, transcript-turn IDs, and exported audio/transcript bytes. There is no automatic historical-episode fork/revision API. Users must create a new episode to change inputs after generation starts.
- **Configuration plan impact:** `EpisodeConfiguration.snapshot()` contains title, focus, audience, technical depth, target duration, style, ordered host IDs, must-cover/avoid topics, source/research/model overrides. Each is part of the planner's canonical request; there is currently no independently mutable, non-plan-affecting episode-configuration field. Therefore only *semantic no-op* saves retain the draft plan, and every meaningful changed snapshot invalidates that draft plan. Plan approval/status changes are a different repository operation and do not require reconfiguring the episode.

## Concurrency and persistence invariants

`EpisodeConfigurationRepository.update` holds `Database.transaction(immediate=True)` while checking `generation_runs`, `conversation_states`, and `conversation_turns`; it updates only when the episode ID, project ID, prior `config_json` (CAS token) and `state='draft'` all match. Ordered host memberships and the affected plan/segments are updated/deleted in this transaction. Any concurrent start, stale config, or injected deletion failure rolls back all edits, including host order.

`EpisodePlanRepository.replace` compares the expected episode config snapshot before writing, rejects stale planner output, and forbids modifying started plan content. `plan_validity.evaluate_episode_plan` checks plan usability; `bind_generation_plan_revision` binds a run to immutable plan content.

## Consumer inventory

| Path | Role |
| --- | --- |
| `episode_config.py`, `storage/episode_configuration.py` | Configuration service, edit policy, host validation, CAS update and plan invalidation |
| `episode_planner.py`, `storage/episode_plan_repository.py` | Plan creation, expected-config CAS, changed-plan rejection after work |
| `plan_validity.py`, `generation_start.py`, `composition.py` | Shared preflight and generation plan validity/revision checks |
| `episode_library_screen.py`, `guided_home.py` | Library and Home latest-run state presentation |
| `guided_episode_wizard.py`, CLI episode commands | Shared configuration, planning and generation service entry points |
| `quick_deep_dive.py` | Creates ordinary draft episodes through shared production services |
| `conversation_generation.py`, `export.py`, transcript/audio services | Consume persisted plan and immutable generated output for review/playback/export |

## Reproduction and qualifications

`tests/test_second_post_review_episode_lifecycle.py` demonstrates disproof of the *current* no-op plan deletion and completed-row demotion risks: `test_noop_episode_edit_preserves_plan_segment_and_episode_identity`, `test_semantically_identical_mapping_order_is_a_true_noop`, `test_non_draft_episode_edit_cannot_demote_state_or_delete_plan` (planned/running/paused/failed/completed), `test_episode_edit_plan_impact_matrix_invalidates_only_meaningful_draft_changes` (all snapshot-field variants), stale planner/edit races, atomic rollback on injected plan-deletion failure, and cross-project host validation. The shared `second_post_review_acceptance` fixture in `tests/conftest.py` feeds `tests/test_second_post_review_acceptance_matrix.py`: two independent completed/exported projects with stable plan/turn/run identities and transcript/audio byte digests, plus a pending run that rejects changed config.

**Remaining work, not claimed complete:** exhaustive TUI/CLI edit and export qualification, failed/paused historical artifact restart matrices, plan-status metadata acceptance, UX for new revisions, and final independent review. Any checkboxes for these remain open.
