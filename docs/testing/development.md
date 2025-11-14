# Development Testing Plan

This guide documents how to exercise the ragadmin/ragman stack end-to-end today. It assumes Ollama, Weaviate, and Phoenix are already running locally. Because `ragadmin init` and `ragadmin health` are not implemented yet, a few bootstrap steps must be performed manually.

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

3. Create a minimal `${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml` using the sample in `specs/001-rag-cli/quickstart.md`.

## 2. Launch the Backend

Run the backend entrypoint with the local service URLs:

```bash
PYTHONPATH=backend/src uv run --directory backend python -m main \
  --config "${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml" \
  --socket "${XDG_RUNTIME_DIR:-/tmp}/ragcli/backend.sock" \
  --weaviate-url http://127.0.0.1:8080 \
  --ollama-url http://127.0.0.1:11434 \
  --phoenix-url http://127.0.0.1:6006 \
  --log-level INFO
```

Add `--trace` if you need the optional deep diagnostics controller.

## 3. Seed the Catalog (Manual Bootstrap)

Until `ragadmin init` lands, register sources directly:

```bash
go run ./cli/ragadmin sources add --type man  --path /usr/share/man
go run ./cli/ragadmin sources add --type info --path /usr/share/info
# add kiwix or other sources as needed:
go run ./cli/ragadmin sources add --type kiwix --path /data/linuxwiki_en.zim
```

Use `ragadmin sources list/update/remove` to verify the catalog. Audit entries are appended under `${XDG_DATA_HOME:-$HOME/.local/share}/ragcli/audit.log`.

## 4. Reindex the Knowledge Base

```bash
go run ./cli/ragadmin reindex
```

Watch Phoenix traces/logs for Ollama/Weaviate health, since `ragadmin health` is not yet available.

## 5. Exercise ragman

Once reindexing succeeds:

```bash
go run ./cli/ragman query "How do I change file permissions?"
```

Test additional options (`--json`, `--plain`, `--context-tokens`, conversation IDs) and confirm confidence thresholds plus citations behave as specified.

## 6. Troubleshooting Tips

- If tests or builds start failing inexplicably, run `make clean DEEP_CLEAN=1` to wipe repo artifacts plus `~/.cache/uv` and `~/.cache/pip`, then recreate the venv.
- For service readiness, hit Ollama/Weaviate health endpoints directly or inspect backend logs until `ragadmin health` is implemented.
- Keep `ragadmin`/`ragman` binaries pointed at `${XDG_RUNTIME_DIR:-/tmp}/ragcli/backend.sock`; delete stale sockets if CLIs fail to connect.
