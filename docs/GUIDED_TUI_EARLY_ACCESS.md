# Guided TUI: early access

**Status: in progress.** These notes describe the implemented production
workflow, not completion of the full guided-workflow specification.

Run `deeper-dive-tui`. An unready installation opens First-run Setup;
a ready configuration opens Home. Skip Setup opens Home without marking
setup complete. The Welcome step offers Quick and Advanced setup depth.
System Check reports Python, FFmpeg, KittenTTS, Ollama and llama-server.
Optional local components are not prerequisites for inspecting projects.
System Check Details shows sanitized diagnostics.

Press **Ctrl+G** to open New Deep Dive. Enter a project name and main
curiosity prompt, then select **Create Project**. This persists through
`DeeperDiveService.create_project`. Continue to Sources, enter a source
title and pasted text, and select **Add Source**. Import and indexing use
the production corpus service. The resulting project and source are durable.

Use **Tab** and **Shift+Tab** to change focus, **Enter** to activate
controls, **Back** to revisit steps, **F1** or **?** for help, and
**Escape** for Save and Exit. Minimum terminal size: **80x24**;
recommended: **100x30**.

**Not yet complete:** guided provider setup, model tests, voice selection,
research, host assignment, planning, generation, review, export, and full
restart/resume acceptance. Existing advanced TUI screens and CLI remain
available. A visible wizard step does not imply that its production
prerequisites are ready. Generation still requires shared preflight.
