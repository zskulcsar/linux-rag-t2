# Quickstart Guide

## Prerequisites
- Linux workstation with Go 1.23+, Python 3.12+, and `uv` installed.
- Local Ollama service running with the required models pulled:
  ```bash
  ollama pull gemma3:1b
  ollama pull embeddinggemma:latest
  ```
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
            "${XDG_DATA_HOME:-$HOME/.local/share}/ragcli/kiwix" \
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
   This seeds the default `man-pages` and `info-pages` sources, writes `${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml`, and prepares the kiwix content directory.
2. Verify dependencies and storage:
   ```bash
   go run ./cli/ragadmin health
   ```
   Health output lists each component (disk, index freshness, source access, Ollama, Weaviate) with pass/warn/fail status and concise remediation hints. Disk warnings appear when free space drops below 10% and failures when it falls to 8% or lower; FAIL takes precedence if both thresholds apply. Index builds older than 30 days warn until a reindex completes.
3. Review seeded sources and register additional content:
   ```bash
   go run ./cli/ragadmin sources list
   go run ./cli/ragadmin sources add --type kiwix --path /data/linuxwiki_en.zim
   ```
4. Trigger ingestion (if not automatic):
   ```bash
   go run ./cli/ragadmin reindex
   ```
   Progress output reports the current stage (e.g., discovering, vectorizing) and, when available, percentage complete.
5. Inspect the generated configuration to tune presenters or confidence threshold:
   ```bash
   cat "${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml"
   ```
   Adjust `ragman.confidence_threshold` or default presenters as needed.

## Query Workflow
1. Ask a question:
   ```bash
   go run ./cli/ragman query "How do I change file permissions?"
   ```
2. Inspect citations and confidence in the CLI output; rerun with `--plain` for unformatted text or `--json` for the raw backend payload.
3. Override context size or provide a conversation token when needed:
   ```bash
   go run ./cli/ragman query "Fix SSH permissions" \
     --context-tokens 6144 \
     --conversation ssh-hardening
   ```
   If the answer falls below the configured confidence threshold, the CLI returns the fixed guidance message “Answer is below the confidence threshold. Please rephrase your query.”

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
