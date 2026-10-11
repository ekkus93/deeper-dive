# Shared typed user defaults and Quick Deep Dive contracts — SPR-04

**Evidence baseline:** source and regressions at `9c3c91459558b40283baa44225cfae395813b3ea`, exact-head [CI #38118100638](https://github.com/ekkus93/deeper-dive/actions/runs/38118100638), quality `114407016271` and fresh-machine `114407016167` (both passed). Earlier `366ec6ffa84cb6cf047852b298334c35e9bdf54e` passed [CI #2548](https://github.com/ekkus93/deeper-dive/actions/runs/38117450369).

## Authoritative storage and writer boundaries

`UserConfig.defaults` is a string-keyed nonsecret mapping in `src/deeper_dive/user_config.py`. `UserConfig.validate_defaults` validates recognized value families using `ResearchMode` from `research_policy.py` and `preset_names()` from `hosts.py`, rather than maintaining a divergent copy of allowed names. `UserConfigStore.validate_candidate` re-parses even mutated Pydantic objects before writing. `save` serializes/validates before unique temporary creation and atomic replacement and rejects concurrent stale revisions. `ProviderController._commit_candidate` validates references and builds complete runtime providers *before* persistence/publication; `SettingsController.set_defaults` processes a batch and saves once.

## Keys, normalization and consumer inventory

| Default keys | Accepted persisted semantics | Primary production readers/writers |
| --- | --- | --- |
| `research_policy`, `quick_deep_dive_research_policy` | Trimmed lowercase `ResearchMode` enum: off/conservative/useful/aggressive; blank clears; Quick override wins over global | `SettingsController.save_research_defaults` / `save_quick_deep_dive_defaults`; `GuidedFirstRunWizard`; `QuickDeepDiveService._apply_overrides`, `guided_readiness`, `ResearchPolicyStore` |
| `quick_deep_dive_duration_minutes` | Trimmed positive integer; blank resets to builtin; **currently no app-specific upper bound** | `SettingsController.save_quick_deep_dive_defaults`, guided first run, `QuickDeepDiveService`; project `quick_deep_dive.duration_minutes` overrides user |
| `quick_deep_dive_host_presets` | Exactly two comma-separated production `preset_names()` (or blank for fallback); duplicates are not currently prohibited | Settings, `GuidedFirstRunWizard`, `QuickDeepDiveService`; project `quick_deep_dive.host_presets` overrides user; validate full pair before creating hosts |
| Seven model roles: `corpus_analysis`, `research_planning`, `source_analysis`, `episode_planning`, `directing`, `host_generation`, `verification` | `provider:model`, trimmed; recognized historical bare-model IDs permitted only on legacy load/rewrite with recorded compatibility context | `SettingsController.save_model_default`, `ProviderController.validate_default_references`, `model_roles`, `preflight`, `composition`, first run |
| `tts_provider`, `tts_voice`, `tts_voice_host_1`, `tts_voice_host_2`, `speech_setup` | Trim whitespace; speech setup configured/deferred; provider identity must reference a configured TTS adapter; voice existence is established at runtime discovery/preflight (not fully validated at save) | `SettingsController.save_tts_defaults`, first-run speech/voice, Quick hosts, preflight/voice readiness |
| `network_policy` | Trimmed, lowercase hyphen alias; local-only / configured-providers / allow-remote / remote-allowed | Settings, `network_scope`, production preflight and research/network controls |
| `local_only` | Trim/lowercase boolean vocabulary: 0/1, true/false, yes/no, off/on | Settings and provider/network consumers |
| `local_provider_ids` | Trimmed comma list; referenced providers validated by `ProviderController` | Settings and provider/network scope |
| `diagnostic_logging` | off/normal/verbose (trimmed lowercase) | `SettingsController.save_runtime_defaults`, diagnostics |
| `ffmpeg_executable`, `kitten_model_dir` | Trimmed single-line non-NUL filesystem path/executable name; actual installation checked at runtime | Settings runtime defaults/readiness, FFmpeg/Kitten flows |
| Unknown legacy/extension keys | Preserved verbatim to avoid destructive config migration | `UserConfigStore.load/save`; future consumer responsibility |

**CLI boundary:** current CLI mutates projects, episodes, research and hosts through their production controllers; there is no separately implemented global `UserConfig.defaults` CLI mutation command. Do not invent a CLI defaults-writer when assessing shared normalization. Project Quick JSON instructions are *overrides*, not global settings, and are validated at the shared Quick consumer before host/episode creation.

## Qualification, disconfirmed risks and remaining gaps

- `tests/test_second_post_review_config_security.py`: invalid global/Quick research, bad duration/host presets, normalized valid and legacy keys, invalid runtime/network defaults, mutated-invalid config rejected before write, restart and Settings-to-Quick integration. `test_research_mode_production_contract_round_trip` iterates all production enum values; `test_each_production_host_preset_is_valid_in_settings_and_quick` iterates all registered production presets.
- `tests/test_second_post_review_quick_project_overrides.py` guards the previously uncovered **partial host creation** risk: invalid first/second project preset or incomplete pair is rejected before any host/episode write; a valid pair creates two hosts. Core fix in `quick_deep_dive.py` validates every project override preset with `preset_names()`. This is a user-facing production fix, not a mock-layer validation.
- `tests/test_second_post_review_config_durability.py`, `tests/test_second_post_review_config_failure_matrix.py`, and `tests/test_second_post_review_controller_writer_races.py` cover atomic batch persistence and explicit concurrency conflicts.
- **Not yet accepted:** authoritative bounded maximum Quick duration (large integer overflow risk), exhaustive voice/provider runtime identity validation at settings-write time, a complete all-surface invalid/legacy/restart matrix, every CLI/TUI security canary, and final independent acceptance. Do not check those items merely because the shared validators exist. Any reconciliation-only edit must itself receive exact-head CI before final acceptance.
