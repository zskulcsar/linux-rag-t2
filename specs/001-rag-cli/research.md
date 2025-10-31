# Research

## Runtime Baselines
- Decision: Target Go 1.23 for the Cobra CLIs and Python 3.12 for the backend, managed with Go modules and uv-managed Python environments.
- Rationale: Go 1.23 provides the stable `log/slog` API and mature Unix socket support needed for structured logging and IPC, while the repo’s `pyproject.toml` already mandates Python ≥3.12; aligning on the current stable versions keeps security support windows wide and tooling consistent across CI.
- Alternatives considered: Go 1.22 (slower security cadence and older stdlib logging) and Python 3.11 (conflicts with declared project requirement and loses 3.12 performance improvements).

## CLI Architecture & Cobra Usage
- Decision: Model `ragman` and `ragadmin` as separate Cobra roots sharing a common `internal/cli` Go package, using PersistentPreRun hooks for dependency injection, mutually exclusive flag guards, and subcommand packages per Cobra best practices.
- Rationale: Context7 Cobra guidance highlights hook ordering, validation helpers, and flag exclusivity APIs, enabling predictable command lifecycle management and DRY flag validation while keeping binaries independent.
- Alternatives considered: `urfave/cli` (less native support for nested commands) and a single multi-mode binary (breaks requirement for standalone executables and complicates UX).

## IPC Protocol & Transport
- Decision: Implement newline-delimited JSON messages over Unix domain sockets using Go’s `net.DialUnix`/`UnixConn` and Python’s `asyncio.start_unix_server`, framing each request with a length prefix header plus UTF-8 payload and including correlation IDs.
- Rationale: Staying within stdlib on both sides avoids third-party protocol dependencies, keeps the transport offline-friendly, and lets us layer request tracing while satisfying the Unix socket requirement; JSON keeps contracts human-inspectable for debugging.
- Alternatives considered: gRPC over Unix sockets (adds protobuf/toolchain overhead), HTTP over Unix sockets (heavier framing, unnecessary for CLI round-trips), and custom binary formats (harder to debug and extend).

## Backend Data & Retrieval Flow
- Decision: Use the Weaviate Python client’s dynamic batching (`with client.batch as batch: ...`) for ingestion, store content classes partitioned by source type, and derive embeddings via Ollama’s `embeddings` API before pushing vectors to Weaviate.
- Rationale: Dynamic batching (per Context7 docs) auto-tunes batch size/concurrency, preventing silent failures and respecting local resource limits; segregating classes by source keeps hybrid search filters simple, and Ollama embeddings keep all inference local.
- Alternatives considered: Fixed-size batching (risk of misconfigured batch sizes) and delegating vectorization to Weaviate modules (would require managing Weaviate plugins beyond current scope).

## Observability & Logging
- Decision: Standardize on structured JSON logging (`log/slog` JSON handler in Go, `structlog` + stdlib logging in Python) with mandatory function-entry log statements, propagate correlation IDs from CLI to backend, and enable Phoenix auto-instrumentation via `phoenix.otel.register(..., auto_instrument=True)` plus relevant instrumentors (e.g., LangChain/LlamaIndex equivalents for our stack).
- Rationale: Phoenix documentation shows turnkey instrumentation hooks that emit traces to the Phoenix UI; combining that with structured logs meets Constitution V while keeping CLI and backend diagnostics aligned.
- Alternatives considered: Using `zap`/`logrus` (adds dependencies without extra value) or manual OTLP exporters (duplicated effort compared to Phoenix’s helpers).

## Testing Strategy
- Decision: Use Go’s built-in `testing` package with table-driven tests for command adapters, add CLI contract tests invoking compiled binaries against a fixture backend socket, and rely on `pytest` + `pytest-asyncio` for backend domain/unit tests alongside mypy strict checks.
- Rationale: Built-in Go testing keeps the CLI lightweight, while CLI contract tests ensure Cobra flag wiring stays in sync with backend expectations; `pytest-asyncio` covers the async Unix socket server and integrates cleanly with coverage gates mandated by the constitution.
- Alternatives considered: Ginkgo/Gomega (heavier DSL not needed) and unittest (less ergonomic for async flows).

## Performance & Resource Targets
- Decision: Budget <500 ms for retrieval/grounding, <5 s for Ollama generation, and <8 s total p95 response time per question, while keeping steady-state memory under 4 GiB and CPU under 4 cores on a developer laptop.
- Rationale: Ensures responsive CLI UX while acknowledging local LLM latency; resource caps align with typical workstation specs and keep the solution usable without dedicated hardware.
- Alternatives considered: No explicit targets (risks slow UX) and stricter sub-second end-to-end goals (unrealistic with local LLM inference).

## Filesystem & Deployment Layout
- Decision: Adopt XDG base directories—store configs under `$XDG_CONFIG_HOME/ragcli`, data/index assets under `$XDG_DATA_HOME/ragcli`, runtime sockets under `$XDG_RUNTIME_DIR/ragcli` (falling back to `/tmp/ragcli` when undefined), and keep Go sources under `cli/` with backend under `services/rag_backend/`.
- Rationale: XDG paths are standard on Linux, preventing clutter in `$HOME`; aligning source layout across `cli/` and `services/` keeps modules independently buildable per Constitution IV.
- Alternatives considered: Hard-coding paths in the project root (breaks multi-user machines) and mixing Go/Python under one src directory (violates hexagonal separation and build independence).

## External Dependency Verification
- Decision: Implement `ragadmin health` checks that hit Ollama’s `/api/tags` and `/api/embeddings` endpoints plus Weaviate’s readiness endpoints, surfacing failures with actionable guidance; expose backend health snapshots over the Unix socket for CLI consumption.
- Rationale: Meets FR-005 verification requirement without managing the services themselves and keeps health reporting consistent between CLI and backend.
- Alternatives considered: Shelling out to service CLIs (less portable) or embedding service orchestration (out of scope per requirements).

## Automation & CI Guardrails
- Decision: Track Python dependencies with `uv lock`, add Ruff/mypy/pytest to CI, introduce a Go workspace with `go.mod` per CLI plus `golangci-lint` for static checks, and ensure Phoenix/Weaviate mocks run during tests to keep pipelines hermetic.
- Rationale: Aligns with the constitution’s automation mandates while keeping Go and Python toolchains isolated yet reproducible.
- Alternatives considered: Relying on ad-hoc pip/go get (non-hermetic) or skipping Go linting (violates governance expectations).
