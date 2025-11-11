# ragadmin CLI (administration interface)

`ragadmin` provides administrative commands for managing knowledge sources,
triggering reindex operations, and validating environment readiness for the
Linux RAG deployment.

## Command Overview

- `ragadmin init`: Seed default sources (`man-pages`, `info-pages`), ensure XDG
  directories exist, and verify baseline dependencies.
- `ragadmin sources list`: Display the current source catalog and metadata.
- `ragadmin sources add --type <man|kiwix|info> --path <path>`: Register new
  sources, invoking validation checks defined in the data model.
- `ragadmin sources remove <alias>`: Remove or quarantine an existing source.
- `ragadmin sources update <alias>`: Replace metadata for an existing source
  while retaining the fixed alias.
- `ragadmin reindex`: Kick off ingestion and index rebuild while streaming
  progress events (stage + optional percent complete).
- `ragadmin health`: Execute readiness checks for disk thresholds, index
  freshness, Weaviate, and Ollama, surfacing remediation guidance.

## Shared Flags

| Flag | Description |
|------|-------------|
| `--output {table,json}` | Select presenter for command output (default `table`). |
| `--socket <path>` | Override the backend Unix socket path (defaults to `${XDG_RUNTIME_DIR:-/tmp}/ragcli/backend.sock`). |

## Audit Logging

Administrative commands append JSON lines to the audit ledger located under
`${XDG_DATA_HOME:-$HOME/.local/share}/ragcli/audit.log`. Entries follow the
contract described in `specs/001-rag-cli/data-model.md`.

## Health Check Semantics

`ragadmin health` evaluates the components enumerated in FR-005:

- **index_freshness**: WARN when the active index is ≥30 days old, FAIL if
  stale or missing.
- **disk_capacity**: WARN when free space ≤10%, FAIL when ≤8%.
- **source_access**: Verify readability of each active knowledge source.
- **ollama / weaviate**: Probe with exponential backoff (0.5s, 1s, 2s, 4s, 8s)
  and 3s per-attempt timeout.

Results render in both table and JSON formats, preserving the component
ordering and severity mapping.

## Documentation Roadmap

- Cobra-generated reference docs will augment this guide once subcommands and
  flags are implemented in `cli/ragadmin/cmd/`.
- Integration with MkDocs ensures `make docs` rebuilds the latest CLI
  documentation whenever command definitions change.
