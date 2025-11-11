# Tooling & Runtime Dependencies

| Task ID | Required tool/dependency | Status | Installation command |
|---------|--------------------------|--------|----------------------|
| T001    | go (>=1.23)              | Present (go1.25.3) | N/A |
| T002    | direnv                   | Present (2.32.1) | N/A |
| T006    | uv                       | Present (0.8.22) | N/A |
| T006    | python3 (3.12.x)         | Present (3.12.3) | N/A |
| T007    | pytest                   | Missing on PATH (run via `uv run pytest` or `uv sync`) | `uv sync` |
| T017    | ollama                   | Present (0.12.5) | N/A |
| T017    | podman                   | Present (fails without writable `/run/user/1000`; set `XDG_RUNTIME_DIR`) | N/A |
| T027    | golangci-lint            | Present (v1.64.8) | N/A |
