# Implementation Plan: Local Linux RAG CLI

**Branch**: `001-rag-cli` | **Date**: 2025-10-31 | **Spec**: `/home/zsoltk/git/linux-rag-t2/specs/001-rag-cli/spec.md`
**Input**: Feature specification from `/specs/001-rag-cli/spec.md`

## Summary

Deliver two standalone Go CLIs (`ragman`, `ragadmin`) that communicate with a Python backend over Unix domain sockets to serve local Linux RAG workflows (spec overview). The backend orchestrates document ingestion into Weaviate, queries Ollama-hosted LLMs over HTTP, and emits observability signals through `arize-phoenix`, while the admin CLI verifies external dependencies without managing their lifecycle beyond health checks (see `research.md` – Runtime Baselines & Observability).

## Technical Context

**Language/Version**: Go 1.23 for CLIs, Python 3.12 backend managed via uv (`research.md` – Runtime Baselines)
**Primary Dependencies**: Go `spf13/cobra`, Go stdlib `net/unix`, Python `weaviate-client`, `arize-phoenix`, `structlog`, `pytest-asyncio`, local Ollama HTTP API (`research.md` – CLI Architecture, Backend Data, Observability)
**Storage**: External Weaviate cluster for vectors; XDG-compliant local directories for configs (`$XDG_CONFIG_HOME/ragcli`), data (`$XDG_DATA_HOME/ragcli`), and sockets (`$XDG_RUNTIME_DIR/ragcli` with `/tmp` fallback) (`research.md` – Filesystem & Deployment Layout)
**Testing**: Go table-driven unit tests + CLI contract tests, Python `pytest` with `pytest-asyncio`, strict mypy and Ruff in CI (`research.md` – Testing Strategy)
**Target Platform**: Local Linux environments (amd64, single-user)
**Project Type**: Multi-component monorepo (Go CLIs + Python service)
**Performance Goals**: <500 ms retrieval, <5 s LLM completion, <8 s p95 end-to-end per query (`research.md` – Performance & Resource Targets)
**Constraints**: Offline-only aside from local services, Unix socket transport, steady-state footprint ≤4 GiB RAM and ≤4 CPU cores (`research.md` – Performance & Resource Targets)
**Scale/Scope**: Single-tenant operator with pre-seeded man/kiwix/info sources; future multi-tenant expansion tracked separately (spec Assumptions)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Monorepo layout: Establish `cli/ragman` and `cli/ragadmin` Go modules plus `services/rag_backend` Python package so each artifact builds/tests independently and respects monorepo boundaries (aligned with `specs/001-rag-cli/spec.md` – Project Structure).
- Hexagonal boundaries: Define domain ports for query execution, ingestion, health reporting, and admin workflows; CLIs remain adapters over the Unix-socket transport while backend adapters encapsulate Ollama/Weaviate/Phoenix integrations (`research.md` – CLI Architecture & Backend Data).
- File sizing & focus: Cobra commands live in one file per command with shared helpers under `cli/internal`; Python service splits domain, ports, and adapters into focused modules, adding refactors if files exceed agreed complexity (`plan.md` – Project Structure tree).
- Simplicity (KISS): Stick with newline-delimited JSON over Unix sockets and avoid introducing REST/gRPC layers or orchestration tooling beyond uv, Ollama, and Weaviate (`research.md` – IPC Protocol & Transport).
- Logging strategy: Use Go `log/slog` JSON handler and Python `structlog` to emit constitution-compliant INFO/DEBUG entries with correlation IDs flowing from CLI requests into backend Phoenix traces (`research.md` – Observability & Logging).
- Documentation updates: Generate Cobra help/manpages, add MkDocs sections for CLI usage and backend architecture, and record an ADR documenting the Unix socket protocol and port definitions (`quickstart.md`, `docs/adr/0001-unix-socket-ipc.md`).
- Testing strategy: Implement Go unit tests plus CLI-backend contract suites, Python `pytest` (async + unit) with strict mypy, and add integration smoke tests for Ollama/Weaviate adapters using mocks to satisfy coverage gates (`research.md` – Testing Strategy).
- Observability impacts: Backend exposes health/readiness responses over the socket, streams Phoenix traces/metrics, and provides structured logs; `ragadmin health` surfaces Ollama/Weaviate readiness per FR-005 (`spec.md` – Functional Requirements, `research.md` – Observability & External Dependency Verification).
- Automation & dependencies: Maintain uv lockfiles, manage Go modules per binary, run Ruff/mypy/pytest/golangci-lint/coverage in CI, and document any version bumps impacting release automation (`research.md` – Automation & CI Guardrails).
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

**Structure Decision**: Adopt dedicated Go CLI modules under `cli/`, a Python service under `services/rag_backend/`, mirrored test directories per language, and supporting documentation under `docs/` to preserve independent builds per module (see tree above and references in `research.md` – Filesystem & Deployment Layout).

## Core Implementation Plan

1. **Define IPC transport and contract scaffolding** – Stand up the Unix socket server/client framing, request/response models, and validation helpers using the schema in `specs/001-rag-cli/contracts/backend-openapi.yaml` and transport guidance in `specs/001-rag-cli/research.md` (see “IPC Protocol & Transport”). Deliver framing tests before wiring business logic.
   • Owner: Backend engineer (platform)
   • Effort: 3 engineering days (includes contract test harness)
   • Inputs: Spec FR-001/FR-005, `contracts/backend-openapi.yaml`, `research.md` (IPC)
2. **Model domain services and ports** – Implement core use cases (query orchestration, catalog management, health checks) in `services/rag_backend/domain/` with interfaces under `services/rag_backend/ports/`, aligning entities and state transitions with `specs/001-rag-cli/data-model.md`.
   • Owner: Backend engineer (domain)
   • Effort: 4 engineering days
   • Inputs: `data-model.md`, Spec Functional Requirements FR-001–FR-011
3. **Wire infrastructure adapters** – Build Weaviate, Ollama, storage, and observability adapters per decisions in `specs/001-rag-cli/research.md` (“Backend Data & Retrieval Flow”, “Observability & Logging”). Ensure Phoenix instrumentation emits trace/log signals that satisfy Constitution V.
   • Owner: Backend engineer (infrastructure)
   • Effort: 5 engineering days
   • Inputs: `research.md` (Backend Data, Observability, Automation), Weaviate/Ollama configs from `quickstart.md`
4. **Expose backend transport API** – Implement the Unix socket adapter in `services/rag_backend/adapters/transport/` so each port maps to the endpoints defined in `contracts/backend-openapi.yaml`, including error semantics for stale indexes (FR-007) and init verification (FR-005).
   • Owner: Backend engineer (platform)
   • Effort: 3 engineering days
   • Inputs: `contracts/backend-openapi.yaml`, Spec Edge Cases, `research.md` (External Dependency Verification)
5. **Build shared Go IPC client** – Create reusable socket client utilities in `cli/shared/ipc/` that marshal requests/responses against the same contract, adding unit tests that mirror backend validation.
   • Owner: Go engineer (shared tooling)
   • Effort: 2 engineering days
   • Inputs: `contracts/backend-openapi.yaml`, `research.md` (IPC), Constitution V logging rules
6. **Implement `ragadmin` commands** – Populate `cli/ragadmin/cmd/` and supporting `internal/app/` use cases to cover init, source CRUD, reindex, and health workflows, referencing functional requirements FR-003 through FR-009 and leveraging catalog fields from `data-model.md`.
   • Owner: Go engineer (admin CLI)
   • Effort: 4 engineering days
   • Inputs: Spec FR-003–FR-011, `data-model.md`, `quickstart.md` (Admin Bootstrap)
7. **Implement `ragman` query flow** – Add query execution, answer rendering, and citation handling in `cli/ragman/`, ensuring confidence and citation outputs respect FR-001/FR-002 and latency metrics defined in `specs/001-rag-cli/research.md` (“Performance & Resource Targets”).
   • Owner: Go engineer (query CLI)
   • Effort: 3 engineering days
   • Inputs: Spec FR-001/FR-002, `research.md` (Performance), `contracts/backend-openapi.yaml`
8. **Contract and integration testing** – Expand `tests/go/contract/` and `tests/python/contract/` to exercise end-to-end CLI↔backend flows, and add observability checks (Phoenix traces, structured logs) to verify compliance with the Constitution and Quickstart expectations in `specs/001-rag-cli/quickstart.md`.
   • Owner: QA engineer (or shared)
   • Effort: 4 engineering days
   • Inputs: `contracts/backend-openapi.yaml`, `quickstart.md`, Constitution III & V mandates

## Verification & Handover Checklist

- **Hexagonal boundaries** – Confirm all transport, storage, and LLM interactions occur via `services/rag_backend/ports/` and adapters; review unit tests for each port to ensure framework-free domain logic (Constitution IV).
- **Observability readiness** – Validate Phoenix tracing/logging by running `uv run pytest tests/python/integration/test_observability.py` (to be authored) and checking structured JSON logs from both CLIs and backend, matching the mandated format (Constitution V). Cross-reference instrumentation decisions in `specs/001-rag-cli/research.md`.
- **Testing gates** – Execute `uv run pytest --cov=services/rag_backend` and `go test ./...` with coverage thresholds ≥80% (service) and ≥90% (libraries) per Constitution III, ensuring contract tests cover `contracts/backend-openapi.yaml`.
- **Documentation updates** – Regenerate Cobra help/manpages, update MkDocs pages under `docs/guides/cli/`, and log the socket protocol ADR (`docs/adr/0001-unix-socket-ipc.md`) before handover (Constitution II).
- **Offline guarantee** – Run `ragadmin init` and `ragadmin health` offline to verify FR-005/FR-010 readiness; confirm error paths mirror spec edge cases and log outcomes to the audit ledger.
- **Automation alignment** – Ensure CI workflows include Ruff, mypy, pytest, golangci-lint, and Phoenix instrumentation smoke tests, with uv lockfile and Go module updates committed (Constitution IV).
- **Release artefacts** – Provide handover notes covering socket endpoints, data model revisions, and test coverage summary so infra/ops can integrate with existing pipelines.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitutional violations requiring waivers have been identified for this plan.
