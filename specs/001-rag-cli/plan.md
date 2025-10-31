# Implementation Plan: Local Linux RAG CLI

**Branch**: `001-rag-cli` | **Date**: 2025-10-31 | **Spec**: `/home/zsoltk/git/linux-rag-t2/specs/001-rag-cli/spec.md`
**Input**: Feature specification from `/specs/001-rag-cli/spec.md`

## Summary

Deliver two standalone Go CLIs (`ragman`, `ragadmin`) that communicate with a Python backend over Unix domain sockets to serve local Linux RAG workflows. The backend orchestrates document ingestion into Weaviate, queries Ollama-hosted LLMs over HTTP, and emits observability signals through `arize-phoenix`, while the admin CLI verifies external dependencies without managing their lifecycle beyond health checks.

## Technical Context

**Language/Version**: Go 1.23 for CLIs, Python 3.12 backend managed via uv  
**Primary Dependencies**: Go `spf13/cobra`, Go stdlib `net/unix`, Python `weaviate-client`, `arize-phoenix`, `structlog`, `pytest-asyncio`, local Ollama HTTP API  
**Storage**: External Weaviate cluster for vectors; XDG-compliant local directories for configs (`$XDG_CONFIG_HOME/ragcli`), data (`$XDG_DATA_HOME/ragcli`), and sockets (`$XDG_RUNTIME_DIR/ragcli` with `/tmp` fallback)  
**Testing**: Go table-driven unit tests + CLI contract tests, Python `pytest` with `pytest-asyncio`, strict mypy and Ruff in CI  
**Target Platform**: Local Linux environments (amd64, single-user)  
**Project Type**: Multi-component monorepo (Go CLIs + Python service)  
**Performance Goals**: <500 ms retrieval, <5 s LLM completion, <8 s p95 end-to-end per query  
**Constraints**: Offline-only aside from local services, Unix socket transport, steady-state footprint ≤4 GiB RAM and ≤4 CPU cores  
**Scale/Scope**: Single-tenant operator with pre-seeded man/kiwix/info sources; future multi-tenant expansion tracked separately

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Monorepo layout: Establish `cli/ragman` and `cli/ragadmin` Go modules plus `services/rag_backend` Python package so each artifact builds/tests independently and respects monorepo boundaries.
- Hexagonal boundaries: Define domain ports for query execution, ingestion, health reporting, and admin workflows; CLIs remain adapters over the Unix-socket transport while backend adapters encapsulate Ollama/Weaviate/Phoenix integrations.
- File sizing & focus: Cobra commands live in one file per command with shared helpers under `cli/internal`; Python service splits domain, ports, and adapters into focused modules, adding refactors if files exceed agreed complexity.
- Simplicity (KISS): Stick with newline-delimited JSON over Unix sockets and avoid introducing REST/gRPC layers or orchestration tooling beyond uv, Ollama, and Weaviate.
- Logging strategy: Use Go `log/slog` JSON handler and Python `structlog` to emit constitution-compliant INFO/DEBUG entries with correlation IDs flowing from CLI requests into backend Phoenix traces.
- Documentation updates: Generate Cobra help/manpages, add MkDocs sections for CLI usage and backend architecture, and record an ADR documenting the Unix socket protocol and port definitions.
- Testing strategy: Implement Go unit tests plus CLI-backend contract suites, Python `pytest` (async + unit) with strict mypy, and add integration smoke tests for Ollama/Weaviate adapters using mocks to satisfy coverage gates.
- Observability impacts: Backend exposes health/readiness responses over the socket, streams Phoenix traces/metrics, and provides structured logs; `ragadmin health` surfaces Ollama/Weaviate readiness per FR-005.
- Automation & dependencies: Maintain uv lockfiles, manage Go modules per binary, run Ruff/mypy/pytest/golangci-lint/coverage in CI, and document any version bumps impacting release automation.
- **Gate Status**: PASS — design artifacts satisfy constitutional guardrails with no outstanding waivers.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
cli/
├── ragman/
│   ├── cmd/                 # Cobra command definitions
│   ├── internal/app/        # CLI orchestration + request assembly
│   └── internal/io/         # Terminal adapters, JSON rendering
├── ragadmin/
│   ├── cmd/                 # Admin commands (init, sources, health, reindex)
│   ├── internal/app/        # Admin use cases
│   └── internal/io/         # Table/JSON formatting, prompts
└── shared/
    └── ipc/                 # Socket client, framing, logging helpers

services/
└── rag_backend/
    ├── domain/              # Core business logic (query, catalog, health)
    ├── ports/               # Interfaces for CLI transport, Ollama, Weaviate, Phoenix
    ├── adapters/
    │   ├── transport/       # Unix socket server implementation
    │   ├── weaviate/        # Vector store adapter
    │   ├── ollama/          # LLM + embedding adapter
    │   ├── storage/         # Catalog persistence (JSON/SQLite)
    │   └── observability/   # Logging + Phoenix instrumentation
    ├── application/         # Use-case orchestrators
    └── telemetry/           # Metrics, tracing helpers

tests/
├── python/
│   ├── unit/
│   ├── integration/
│   └── contract/
└── go/
    ├── unit/
    └── contract/

docs/
├── adr/
│   └── 0001-unix-socket-ipc.md
└── guides/
    └── cli/
        ├── ragman.md
        └── ragadmin.md
```

**Structure Decision**: Adopt dedicated Go CLI modules under `cli/`, a Python service under `services/rag_backend/`, mirrored test directories per language, and supporting documentation under `docs/` to preserve independent builds per module.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitutional violations requiring waivers have been identified for this plan.
