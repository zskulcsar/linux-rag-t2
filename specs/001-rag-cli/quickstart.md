# Quickstart Guide

## Prerequisites
- Linux workstation with Go 1.23+, Python 3.12+, and `uv` installed.
- Local Ollama service running with required models pulled (e.g., `ollama pull llama3.1`).
- Local Weaviate deployment reachable via `http://localhost:8080` (Docker/Podman or native).
- `direnv` configured so `.envrc` exports `CODEX_HOME` and `CONTEXT7_API_KEY` as noted in the project README.

## Environment Setup
1. Sync Python dependencies:
   ```bash
   uv sync
   ```
2. Bootstrap Go worktree:
   ```bash
   go work init ./cli/ragman ./cli/ragadmin
   ```
3. Ensure runtime directories exist (XDG compliant):
   ```bash
   mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/ragcli" \
            "${XDG_DATA_HOME:-$HOME/.local/share}/ragcli" \
            "${XDG_RUNTIME_DIR:-/tmp}/ragcli"
   ```

## Start Backend Service
1. Launch the Python backend (development mode):
   ```bash
   uv run python -m services.rag_backend.main \
     --socket "${XDG_RUNTIME_DIR:-/tmp}/ragcli/backend.sock" \
     --weaviate-url http://localhost:8080 \
     --ollama-url http://localhost:11434
   ```
2. Confirm Phoenix UI is reachable at http://localhost:6006 if observability dashboards are required.

## Administrative Bootstrap
1. Initialize directories and default sources:
   ```bash
   go run ./cli/ragadmin init
   ```
2. Verify dependencies and storage:
   ```bash
   go run ./cli/ragadmin health
   ```
3. Add new sources (examples):
   ```bash
   go run ./cli/ragadmin sources add --type kiwix --path /data/linuxwiki_en.zim
   go run ./cli/ragadmin sources add --type man --path /usr/share/man
   ```
4. Trigger ingestion (if not automatic):
   ```bash
   go run ./cli/ragadmin reindex
   ```

## Query Workflow
1. Ask a question:
   ```bash
   go run ./cli/ragman "How do I change file permissions?"
   ```
2. Inspect citations and confidence in the CLI output; rerun with `--json` for machine-readable responses.

## Testing & Validation
1. Run backend unit tests with coverage:
   ```bash
   uv run pytest --cov=services/rag_backend
   ```
2. Run Go tests (CLIs and shared packages):
   ```bash
   go test ./cli/...
   ```
3. Execute end-to-end contract tests:
   ```bash
   uv run pytest tests/contracts
   ```

## Shutdown & Maintenance
- Stop the backend process with `Ctrl+C`; sockets are recreated on next start.
- Use `ragadmin sources remove <alias>` to quarantine obsolete sources.
- Review audit logs under `${XDG_DATA_HOME:-$HOME/.local/share}/ragcli/audit.log` for administrative traceability.
