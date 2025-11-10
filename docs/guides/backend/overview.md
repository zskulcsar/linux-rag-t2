# Backend Service Overview

The Python backend (`services/rag_backend`) exposes the Unix-socket transport
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
| `structlog` |
| `weaviate-client` |

## Development Dependencies

| Package |
|---------|
| `pytest-asyncio>=0.23` |
| `pytest>=8.0` |

## Key Documents

- **Data Model**: `specs/001-rag-cli/data-model.md`
- **Transport Contract**: `specs/001-rag-cli/contracts/backend-openapi.yaml`
- **Research Notes**: `specs/001-rag-cli/research.md`
- **Tasks & Milestones**: `specs/001-rag-cli/tasks.md`

## Planned Module Layout

```text
services/rag_backend/
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
- `uv run mypy services/rag_backend` under strict settings (Constitution I).

## Observability

The backend emits structured JSON logs using `structlog` and integrates with
`arize-phoenix` via OTEL auto-instrumentation as outlined in
`specs/001-rag-cli/research.md`. Correlation IDs propagate from CLI requests to
log entries and Phoenix traces.

## Configuration

- XDG-compliant directories determine config/data/runtime socket paths.
- Launch the backend with `python -m services.rag_backend.main` (or `make run-backend`)
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
