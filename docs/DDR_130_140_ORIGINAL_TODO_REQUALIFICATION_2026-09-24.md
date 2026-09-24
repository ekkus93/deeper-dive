# DDR-130 through DDR-140 Original TODO Requalification — 2026-09-24

This document records the original `docs/DEEP_DIVE_TUI_TODO.md` semantic requalification for DDR-130 through DDR-140 after the V1 integration remediation work landed. It is evidence for the R14 section of `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md`.

## Qualification baseline

Current `master` at the time of this requalification:

- Commit: `49ad61c98f59a9557028ed7b113c72ede7b9d2b1`.
- Merged-master CI: run `35975814559`, conclusion `success`.
- The same merged-master CI includes the strengthened fresh-machine gate from DDR-110, the full pytest suite, Ruff format/lint, mypy, build, installed-wheel CLI/TUI startup, installed-wheel preflight/generation/export assertions, installed-wheel secret-redaction probe, and the real KittenTTS Micro CPU smoke.

## DDR-130 — Requalify DD-150

DD-150 covered source/host/duration/provider/FFmpeg preflight and the Generate action.

Evidence:

- `tests/test_preflight.py`, `tests/test_preflight_routing.py`, `tests/test_preflight_project_defaults.py`, and `tests/test_preflight_route_ui.py` cover source, host, duration, provider/model assignment, routing disclosure, project defaults, and FFmpeg preflight behavior.
- `tests/test_preflight_generate_integration.py::test_generate_starts_real_pipeline_and_reuses_active_run` verifies that Generate creates/reuses the correct run, starts real orchestration, executes every `DEFAULT_STAGES` entry, and reaches `completed`.
- `tests/test_tui.py::test_preflight_generate_click_starts_pipeline` covers the TUI Generate click path.
- `tests/test_composition_effective_config.py` and `tests/test_effective_config.py` cover episode/project/user assignment precedence consumed by preflight and generation.
- The strengthened fresh-machine CI gate on `49ad61c98f59a9557028ed7b113c72ede7b9d2b1` now validates installed-wheel preflight before actual generation.

Conclusion: DD-150 semantics are requalified.

## DDR-131 — Requalify DD-151

DD-151 covered the Generation Monitor, real runner wiring, orchestration controls, transcript navigation, and diagnostics.

Evidence:

- `tests/test_generation_monitor.py` and `tests/test_generation_monitor_production.py` cover monitor snapshots, stage/current-turn/recent-turn binding, production runner wiring, transcript review navigation, and sanitized diagnostic/failure presentation.
- `tests/test_ddr105_run_state_matrix.py` covers pending/running/paused/resumed/failed/completed transitions, restart checkpoint reuse, and illegal terminal resume rejection.
- `tests/test_pipeline_control_transitions.py`, `tests/test_ddr062_cli_control.py`, and `tests/test_ddr111_cli_acceptance.py` cover durable pause, cancel, and resume semantics through production pipeline/CLI paths.
- `tests/test_ddr107_security_regression_matrix.py`, `tests/test_diagnostics.py`, and `tests/test_error_redaction_surfaces.py` cover sanitized diagnostics across persisted state, logs, CLI-visible output, and TUI-visible output.

Conclusion: DD-151 semantics are requalified.

## DDR-132 — Requalify DD-152

DD-152 covered Episode Library resume/export and retained library-state behavior.

Evidence:

- `tests/test_episode_library_screen.py` covers Episode Library listing/state behavior and selected-episode actions.
- `tests/test_episode_library_export_integration.py` and `tests/test_ddr031_export_qualification.py` cover production-composed Episode Library export through `EpisodeExporter`, actual transcript/manifest/metadata/audio files, output paths, incomplete-run rejection, episode identity, and provenance metadata.
- `tests/test_ddr105_run_state_matrix.py`, `tests/test_ddr062_cli_control.py`, and `tests/test_ddr111_cli_acceptance.py` cover resume through durable orchestration/checkpoint state.
- `tests/test_ddr104_multi_episode_isolation.py` and `tests/test_ddr104_episode_mutation_isolation.py` cover multi-episode library/export isolation and duplicate/delete non-contamination.

Conclusion: DD-152 semantics are requalified.

## DDR-133 — Requalify DD-153

DD-153 covered Transcript Review, targeted regeneration, episode-specific playback, and direct screen tests.

Evidence:

- `tests/test_transcript_review_screen.py` covers screen-level turn/section repair, production-composed targeted repair service use, missing-provider failure handling, regenerated TTS/audio artifacts, refreshed timelines, and selected-episode audio identity.
- `tests/test_targeted_repair.py` and `tests/test_targeted_repair_section.py` cover targeted turn and section regeneration service behavior.
- `tests/test_ddr102_transcript_review_direct.py` covers chapter/turn rendering, claims, citation rendering, source-passage presentation, and selected-episode transcript-review export.
- `tests/test_transcript_review_audio_identity.py`, `tests/test_transcript_audio_identity.py`, and `tests/test_transcript_audio_isolation.py` cover episode-specific audio identity and isolation.

Conclusion: DD-153 semantics are requalified.

## DDR-134 — Requalify DD-154 regressions

DD-154 covered playback behavior, headless behavior, and process cleanup.

Evidence:

- `tests/test_audio_playback.py` covers terminate/wait, bounded kill escalation, stalled reaping, no-player/headless graceful behavior, and player-process cleanup.
- `tests/test_transcript_review_screen.py::test_transcript_review_resolves_audio_by_selected_episode_identity` verifies selected-episode playback resolution and no arbitrary first-file fallback.
- `tests/test_transcript_audio_identity.py`, `tests/test_transcript_audio_isolation.py`, and `tests/test_audio_regeneration.py` cover audio artifact identity, isolation, and regeneration behavior.

Conclusion: DD-154 semantics are requalified.

## DDR-135 — Requalify DD-155

DD-155 covered Quick Deep Dive defaults/overrides and durable generation/artifacts.

Evidence:

- `tests/test_quick_deep_dive.py` covers built-in defaults, user defaults, project override precedence, existing project hosts, research policy/config persistence, and durable Quick Deep Dive workflow setup.
- `tests/test_ddr041_production_pipeline_artifacts.py` verifies Quick Deep Dive production generation produces durable transcript/audio/exportable artifacts through production composition.
- `tests/test_ddr112_tui_acceptance.py` covers Quick Deep Dive from the TUI path through preflight, Generate click, monitor completion, transcript review, Episode Library navigation, and artifact export.

Conclusion: DD-155 semantics are requalified.

## DDR-136 — Requalify DD-160

DD-160 covered source CLI behavior.

Evidence:

- `tests/test_source_matrix.py` covers file source, directory source, URL source integration, include/exclude/remove behavior, and source metadata.
- `tests/test_cli.py` and `tests/test_episode_cli.py` cover JSON CLI output conventions used by source and episode commands.
- `tests/test_batch_import.py`, `tests/test_parsing.py`, `tests/test_text_markdown_parsing.py`, `tests/test_pdf_parsing.py`, `tests/test_docx_parsing.py`, and `tests/test_html_ingestion.py` cover parser/source-ingestion behavior for the supported source types.

Conclusion: DD-160 semantics are requalified.

## DDR-137 — Requalify DD-161

DD-161 covered research analyze/list/run/ignore/outcomes.

Evidence:

- `tests/test_research_cli.py` covers research CLI command surfaces.
- `tests/test_research_execution_cli.py` covers executing selected/all research gaps and outcome persistence.
- `tests/test_research_gaps.py`, `tests/test_research_candidates.py`, `tests/test_research_fetch.py`, `tests/test_research_matrix.py`, and `tests/test_research_tui.py` cover gap analysis, candidate/outcome handling, safe fetch, policy behavior, and TUI integration.

Conclusion: DD-161 semantics are requalified.

## DDR-138 — Requalify DD-162

DD-162 covered host presets, host creation/editing, project host listing, and voice/provider assignment.

Evidence:

- `tests/test_host_presets.py` covers preset listing and preset-derived host profiles.
- `tests/test_host_behavior.py`, `tests/test_hosts_screen.py`, and `tests/test_multi_host_matrix.py` cover host profile behavior, project host listing, and multi-host matrix behavior.
- `tests/test_episode_cli.py` and `tests/test_ddr111_cli_acceptance.py` cover host creation and use from the CLI workflow.
- `tests/test_provider_tui.py`, `tests/test_providers_tui.py`, `tests/test_voice_preview.py`, and the strengthened fresh-machine gate cover voice/provider assignment and deterministic TTS provider wiring.

Conclusion: DD-162 semantics are requalified.

## DDR-139 — Requalify DD-163

DD-163 covered episode create/configure/plan/show/generate/control/status/export.

Evidence:

- `tests/test_episode_cli.py` covers create, plan, generate, status, and export through CLI surfaces.
- `tests/test_ddr061_cli_generate.py` covers generation reaching `completed`, persisted turns, completed TTS artifacts, and episode audio.
- `tests/test_ddr062_cli_control.py` covers pause/cancel/resume/status semantics through CLI paths.
- `tests/test_ddr063_cli_export.py` covers shared artifact export from the CLI and validates transcript, manifest, metadata, audio, selected output directory, and completed episode/run identity.
- `tests/test_ddr111_cli_acceptance.py` covers the end-to-end fake-provider CLI workflow and deterministic pause/resume path.

Conclusion: DD-163 semantics are requalified.

## DDR-140 — Requalify DD-164

DD-164 covered provider CLI behavior, configured-provider health/test, model/voice discovery, and Kitten installation/status/benchmark.

Evidence:

- `tests/test_provider_cli.py` covers provider CLI listing, health/test behavior, model discovery, and voice discovery paths.
- `tests/test_provider_factory.py`, `tests/test_provider_matrix.py`, and `tests/test_ddr106_provider_routing_matrix.py` cover configured-provider construction/routing for OpenAI, Ollama, llama-server/OpenAI-compatible, KittenTTS, OpenAI/OpenAI-compatible TTS, ElevenLabs, missing credentials, invalid providers, and local/remote classification without paid live credentials.
- `tests/test_kitten_model_manager.py`, `tests/test_kitten_tts.py`, and `tests/test_tts_benchmark.py` cover Kitten model manager/status/runtime and benchmark output behavior.
- The strengthened fresh-machine CI gate preserves the real KittenTTS Micro CPU smoke as a separate bounded qualification step.

Conclusion: DD-164 semantics are requalified.

## Final R14 statement

DDR-130 through DDR-140 have current merged test/evidence coverage and are validated by merged-master CI run `35975814559` on `49ad61c98f59a9557028ed7b113c72ede7b9d2b1`. The remaining work for R14 is TODO checkbox reconciliation in the authoritative remediation TODO.
