# DD-173 Filesystem and process hardening audit

## Project path isolation

`WorkspaceManager` derives project roots only from validated project IDs and resolves project-relative paths through `_require_within`. Absolute paths and traversal outside the resolved project root are rejected. Existing tests cover traversal, absolute paths, malicious project IDs, and isolation between two project workspaces.

## Parser temporary files

Document/source ingestion uses project-scoped source and cache locations rather than user-controlled absolute output paths. Temporary/config writes use sibling temporary files followed by atomic replacement. User-derived readable artifact components are normalized with `sanitize_component`; durable project objects use generated IDs.

## External processes

The FFmpeg composer constructs an argv list and invokes `subprocess.run(..., shell=False)`. The local audio player similarly constructs strategy-specific argv and invokes `subprocess.Popen(..., shell=False)`. User-controlled media paths are passed as individual argv elements rather than interpolated into shell commands. No reviewed external-process path requires `shell=True`.

## Configuration permissions

`UserConfigStore` intentionally excludes credentials from its schema and rejects secret-like unknown fields. On POSIX systems, saved configuration files are now explicitly restricted to mode `0600`, including the temporary file before atomic replacement. Other platforms retain their native ACL semantics rather than applying POSIX mode assumptions.

## DD-173 conclusion

The audited filesystem and process boundaries are fail-closed against project traversal and shell interpolation. Configuration persistence now applies owner-only POSIX permissions where the platform supports them. Any future parser that introduces OS temporary files or any new subprocess call must preserve project isolation, bounded cleanup, argv-only execution, and `shell=False` unless an explicit security review documents an exception.
