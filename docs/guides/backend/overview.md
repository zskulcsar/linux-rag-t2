# Backend Service Overview

The Python backend (`backend/src`) exposes the Unix-socket transport
consumed by the Go CLIs and orchestrates retrieval, ingestion, and health
evaluation workflows. It adheres to the hexagonal architecture decisions
captured in `specs/001-rag-cli/plan.md` and the data contracts codified in
`specs/001-rag-cli/contracts/backend-openapi.yaml`.

## Runtime Metadata

- **Name**: `rag-backend`
- **Version**: `0.1.0`
- **Python Requirement**: `>=3.12`

## Core Dependencies

| Package |
|---------|
| `arize-phoenix` |
| `pyyaml>=6.0` |
| `structlog` |
| `weaviate-client` |

## Development Dependencies

| Package |
|---------|
| `build>=1.2.2` |
| `mkdocs-autoapi>=0.4.1` |
| `mkdocs-material>=9.6.23` |
| `mkdocs>=1.6.1` |
| `mkdocstrings-python>=1.19.0` |
| `mypy>=1.18.2` |
| `pytest-asyncio>=0.23` |
| `pytest>=8.0` |
| `ruff>=0.14.4` |
| `types-pyyaml>=6.0.12.20250915` |

## Key Documents

- **Data Model**: `specs/001-rag-cli/data-model.md`
- **Transport Contract**: `specs/001-rag-cli/contracts/backend-openapi.yaml`
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

Use the Make targets defined in the repo to exercise each layer:

- `make test-unit-py` – Python unit suite (domain, ports, telemetry, launcher helpers) with coverage.
- `make test-contr-py` – Python contract tests validating the Unix-socket transport handlers.
- `make test-int-py` – Python integration suite for adapters/offline guard workflows (requires local Weaviate/Ollama mocks).
- `make test-perf-py` – Python performance harness for ingestion/query SLAs (optional; heavier dependencies).
- `make lint-py` / `make tc-py` – Ruff formatting/linting and strict mypy (`PYTHONPATH=backend/src`) per Constitution I.

## Observability

The backend emits structured JSON logs using `structlog` and integrates with
`arize-phoenix` via OTEL auto-instrumentation as outlined in
`specs/001-rag-cli/research.md`. Correlation IDs propagate from CLI requests to
log entries and Phoenix traces.

## Configuration

- XDG-compliant directories determine config/data/runtime socket paths.
- Launch the backend with `PYTHONPATH=backend/src uv run --directory backend python -m main` (or `make run-be`)
  and provide the required flags:
  - `--socket` (Unix socket path, usually `${XDG_RUNTIME_DIR:-/tmp}/ragcli/backend.sock`)
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
