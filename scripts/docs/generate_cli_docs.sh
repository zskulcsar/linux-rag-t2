#!/usr/bin/env bash
# Generate CLI documentation markdown assets consumed by MkDocs.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DOCS_DIR="$ROOT_DIR/docs/guides/cli"

mkdir -p "$DOCS_DIR"

cat >"$DOCS_DIR/ragman.md" <<'EOF'
# ragman CLI (query interface)

`ragman` is the primary command-line interface for posing English-language
questions against the local Linux RAG backend. The CLI maintains the offline
contract defined in `specs/001-rag-cli/spec.md` and communicates with the
backend over Unix domain sockets.

## Usage

```bash
ragman query "How do I change file permissions?"
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--context-tokens` | `4096` | Maximum token budget forwarded to retrieval (min 512, max 8192). |
| `--conversation` | _(empty)_ | Optional conversation identifier for follow-up questions. |
| `--json` | `false` | Emit raw JSON payload from the backend. |
| `--plain` | `false` | Render plain-text output instead of Markdown. |

The CLI enforces the confidence threshold seeded via
`${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml`. Responses below the
threshold render the fixed fallback guidance defined in FR-002.

## Response Structure

The backend returns a `QueryResponse` JSON object as defined in
`specs/001-rag-cli/contracts/backend-openapi.yaml`. Key fields include:

- `summary`: High-level answer paragraph or low-confidence guidance.
- `steps[]`: Ordered procedural instructions rendered under a numbered list.
- `references[]`: Source citations with labels/URLs used to build the reference table.
- `confidence`: Float between `0` and `1` that drives confidence handling.
- `trace_id`: Correlation identifier propagated through logs and Phoenix traces.

## Example Output

```text
Summary: Use `chmod` with the desired mode to adjust permissions.

Steps:
1. Run `chmod 755 <file>` to grant execute permissions.
2. Verify with `ls -l` to confirm the new mode.

References:
- chmod(1)

Confidence: 0.82
Latency: retrieval 180 ms, llm 900 ms, total 1.2 s
```

## Logging

`ragman` emits structured JSON logs via `log/slog` using the format mandated by
the repository constitution, e.g.:

```text
QueryCommand.Execute(question="How do I change file permissions?") :: starting request
```

## Future Enhancements

- Contract test harness under `tests/go/contract/` exercises framing and JSON
  validation against the backend transport.
- MkDocs pages will be extended with generated Cobra command reference once the
  command tree is implemented.
EOF

cat >"$DOCS_DIR/ragadmin.md" <<'EOF'
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
EOF
