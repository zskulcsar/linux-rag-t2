# Development Testing Plan

This guide documents how to exercise the ragadmin/ragman stack end-to-end on a developer workstation. It assumes Ollama, Weaviate, and Phoenix are already running locally and reachable via `localhost`. The workflow below uses the shipping `ragadmin init` and `ragadmin health` commands so no manual catalog bootstrap is required.

## 1. Prepare the Environment

1. Build the backend virtual environment:

   ```bash
   make venv      # or: uv sync --directory backend
   ```

2. Ensure runtime directories exist (XDG-compliant):

   ```bash
   mkdir -p \
     "${XDG_CONFIG_HOME:-$HOME/.config}/ragcli" \
     "${XDG_DATA_HOME:-$HOME/.local/share}/ragcli" \
     "${XDG_RUNTIME_DIR:-/tmp}/ragcli"
   ```
   
   This will likely create the folders:
   - ~/.config/ragcli
   - ~/.local/share/ragcli
   - /tmp/ragcli

3. (Optional) Inspect or edit `${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml` after `ragadmin init` seeds it. The sample schema lives in `specs/001-rag-cli/quickstart.md`.

## 2. Launch the Backend

Run the backend entrypoint with the local service URLs:

```bash
PYTHONPATH=backend/src uv run --project backend python -m main \
  --config "${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml" \
  --socket "${XDG_RUNTIME_DIR:-/tmp}/ragcli/backend.sock" \
  --weaviate-url http://127.0.0.1:8080 \
  --weaviate-grpc-port 50051 \
  --ollama-url http://127.0.0.1:11434 \
  --phoenix-url localhost:4317 \
  --log-level INFO
```

Add `--trace` if you need the optional deep diagnostics controller.

Alternatively a target is provided in the Makefile called *run-be*, so that `make run-be` runs the same with log level *DEBUG* and *--trace* passed.

## 3. Initialize the Environment

Run the command once per machine to create XDG directories, config, and seed sources:

```bash
go run ./cli/ragadmin init
```

The CLI prints the created directories plus any seeded sources (`man-pages`, `info-pages`). Audit entries are written to `${XDG_DATA_HOME:-$HOME/.local/share}/ragcli/audit.log`.

## 4. Verify Dependencies and Storage

```bash
go run ./cli/ragadmin health
```

Confirm each component (disk capacity, index freshness, source access, Ollama, Weaviate) reports `PASS`/`WARN`/`FAIL` as expected. Use the remediation hints to fix local issues before continuing.

## 5. Reindex the Knowledge Base

```bash
go run ./cli/ragadmin reindex
```

Watch Phoenix traces/logs for Ollama/Weaviate health, since `ragadmin health` is not yet available.

> **Note:** The backend now requires both HTTP **and** gRPC connectivity to Weaviate.
> Ensure your local deployment listens on `:8080` for HTTP and `:50051` for gRPC (the
> defaults in `docs/install/systemd/weaviate.service`). If you change either port,
> update both `weaviate_url` and `weaviate_grpc_port` in the backend config/CLI flags
> before running the steps above.

## 6. Exercise ragman

Once reindexing succeeds:

```bash
go run ./cli/ragman query "How do I change file permissions?"
```

Test additional options (`--json`, `--plain`, `--context-tokens`, conversation IDs) and confirm confidence thresholds plus citations behave as specified.

## 7. Troubleshooting Tips

- If tests or builds start failing inexplicably, run `make clean DEEP_CLEAN=1` to wipe repo artifacts plus `~/.cache/uv` and `~/.cache/pip`, then recreate the venv.
- For service readiness, hit Ollama/Weaviate health endpoints directly or inspect backend logs until `ragadmin health` is implemented.
- Keep `ragadmin`/`ragman` binaries pointed at `${XDG_RUNTIME_DIR:-/tmp}/ragcli/backend.sock`; delete stale sockets if CLIs fail to connect.
- Long-running IPC streams (e.g., `ragadmin reindex`) use a generous per-frame read timeout (5m) and emit heartbeats during ingestion; if the client drops, the server stops writing but continues processing unless configured otherwise.
