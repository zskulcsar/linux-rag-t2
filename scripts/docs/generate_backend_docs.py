"""Generate backend documentation Markdown consumed by MkDocs."""

from __future__ import annotations

import textwrap
from pathlib import Path

import tomllib


ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs" / "guides" / "backend"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

PYPROJECT = ROOT / "services" / "rag_backend" / "pyproject.toml"

project_meta = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

project = project_meta.get("project", {})
dependencies = project.get("dependencies", [])
dev_deps = project_meta.get("dependency-groups", {}).get("dev", [])

dependency_table = "\n".join(
    f"| `{dep}` |" for dep in sorted(dependencies)
) or "| _None declared_ |"

dev_dependency_table = "\n".join(
    f"| `{dep}` |" for dep in sorted(dev_deps)
) or "| _None declared_ |"

data_model_path = ROOT / "specs" / "001-rag-cli" / "data-model.md"
contracts_path = ROOT / "specs" / "001-rag-cli" / "contracts" / "backend-openapi.yaml"

## TODO: source this text from a markdown template instead of embedding here
content = f"""# Backend Service Overview

The Python backend (`services/rag_backend`) exposes the Unix-socket transport
consumed by the Go CLIs and orchestrates retrieval, ingestion, and health
evaluation workflows. It adheres to the hexagonal architecture decisions
captured in `specs/001-rag-cli/plan.md` and the data contracts codified in
`{contracts_path.relative_to(ROOT)}`.

## Runtime Metadata

- **Name**: `{project.get('name', 'rag-backend')}`
- **Version**: `{project.get('version', '0.0.0')}`
- **Python Requirement**: `{project.get('requires-python', '>=3.12')}`

## Core Dependencies

| Package |
|---------|
{dependency_table}

## Development Dependencies

| Package |
|---------|
{dev_dependency_table}

## Key Documents

- **Data Model**: `{data_model_path.relative_to(ROOT)}`
- **Transport Contract**: `{contracts_path.relative_to(ROOT)}`
- **Research Notes**: `specs/001-rag-cli/research.md`
- **Tasks & Milestones**: `specs/001-rag-cli/tasks.md`

## Planned Module Layout

```text
backend/src/
├── domain/              # Core business logic
├── ports/               # Request/response interfaces
├── adapters/
│   ├── transport/       # Unix socket server implementation
│   ├── weaviate/        # Vector store adapter
│   ├── ollama/          # LLM & embedding adapter
│   ├── storage/         # Catalog + audit persistence
│   └── observability/   # Phoenix + logging instrumentation
├── application/         # Use-case orchestration
└── telemetry/           # Metrics helpers
```

## Testing Strategy

- `uv run pytest tests/python/unit` for domain and port validation.
- `uv run pytest tests/python/integration` for adapter behaviour with mocks.
- `uv run pytest tests/python/contract` to ensure transport compliance.
- `uv run pytest tests/python/performance` to ensure performance compliance.
- `PYTHONPATH=backend/src uv run --directory backend mypy backend/src` under strict settings (Constitution I).

## Observability

The backend emits structured JSON logs using `structlog` and integrates with
`arize-phoenix` via OTEL auto-instrumentation as outlined in
`specs/001-rag-cli/research.md`. Correlation IDs propagate from CLI requests to
log entries and Phoenix traces.

## Configuration

- XDG-compliant directories determine config/data/runtime socket paths.
- Launch the backend with `PYTHONPATH=backend/src uv run --directory backend python -m main` (or `make run-be`)
  and provide the required flags:
  - `--socket` (Unix socket path, usually `${{XDG_RUNTIME_DIR:-/tmp}}/ragcli/backend.sock`)
  - `--weaviate-url` (HTTP endpoint for the local Weaviate instance)
  - `--ollama-url` (HTTP endpoint for the Ollama runtime)
  - `--phoenix-url` (HTTP endpoint for the Phoenix UI)
  - `--log-level` (optional stdlib logging verbosity, defaults to `INFO`)
  - `--trace` (optional flag that enables the telemetry `TraceController`)
- Offline enforcement is always active, meaning any outbound TCP connection
  targeting non-loopback hosts raises an `OfflineNetworkError`.

## Roadmap

Implementation of port definitions, domain services, and adapters is tracked in
Phase 2 tasks (T013–T025). Future documentation updates should capture:

1. Concrete module APIs once the domain and ports are implemented.
2. Example transport payloads for `/v1/query`, `/v1/sources`, and health routes.
3. Observability dashboards and Phoenix workflow instructions.
"""

target = DOCS_DIR / "overview.md"
target.write_text(textwrap.dedent(content), encoding="utf-8")
