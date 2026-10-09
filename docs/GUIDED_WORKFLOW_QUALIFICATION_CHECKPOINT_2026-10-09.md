# Guided workflow qualification checkpoint

Qualified master head: 73080c2d7d9691ac9fb845c6b18d7e5a4d1ccbbe
Exact-head CI: 37879730927 (passed quality and fresh-machine).

Completed on master:
- Two guided episodes and multiple durable pipeline turns are checked in the canonical TODO, backed by test_two_guided_episodes_within_one_project_keep_artifacts_isolated.
- Typed input preservation is checked, backed by test_guided_project_and_episode_local_errors_render_inline_without_losing_input.
- tests/test_guided_restart_compatibility.py covers a fresh-process reload of an existing provider, project, source corpus, and Home/Library navigation. CI 37878813707 passed on its first source-qualified head; subsequent source assertions passed at the current head.
- tests/test_guided_viewport_matrix.py exercises first-run and New Deep Dive at 100x30, 80x24, 79x24, and 80x23, asserting the resize warning, preserved state, and in-bounds shared primary actions.

Remaining TODO reconciliation after qualification: GW-250 inline field validation and viewport checks; GW-270 persisted provider/project/source compatibility; GW-290 matrix evidence. These must be checked only against qualified exact-head CI. Other GW-250/GW-270/GW-290 tasks remain genuinely open.
