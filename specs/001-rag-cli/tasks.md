# Tasks: Local Linux RAG CLI

## Milestone 1 – IPC transport scaffold (Plan step 1)
- [ ] Implement backend Unix socket server skeleton (`services/rag_backend/adapters/transport/server.py`) using contract schema.
- [ ] Implement Go IPC client framing utilities (`cli/shared/ipc/client.go`).
- [ ] Add request/response validation tests referencing `contracts/backend-openapi.yaml`.

## Milestone 2 – Domain services & ports (Plan step 2)
- [ ] Define query, ingestion, health ports in `services/rag_backend/ports/`.
- [ ] Implement domain services in `services/rag_backend/domain/` covering FR-001–FR-011.
- [ ] Author unit tests for domain logic (pytest + mypy strict).

## Milestone 3 – Infrastructure adapters (Plan step 3)
- [ ] Create Weaviate adapter (ingest/query) with dynamic batching per `research.md`.
- [ ] Create Ollama adapter for embedding + generation with latency metrics.
- [ ] Implement catalog storage and audit logging adapters honoring XDG paths.
- [ ] Wire Phoenix instrumentation (`arize-phoenix`) and structured logging.

## Milestone 4 – Transport endpoints (Plan step 4)
- [ ] Map domain ports to `/v1/*` handlers in transport adapter with error semantics.
- [ ] Add init verification path covering FR-005 (Weaviate + Ollama checks).
- [ ] Extend contract tests to cover stale index and init failure flows.

## Milestone 5 – Shared Go IPC client (Plan step 5)
- [ ] Implement request builders and response decoders shared by CLIs.
- [ ] Add retry/backoff logic for transient Unix socket failures.
- [ ] Cover with Go unit tests mirroring backend contract validation.

## Milestone 6 – `ragadmin` CLI (Plan step 6)
- [ ] Scaffold Cobra root and subcommands (init, sources, reindex, health).
- [ ] Implement presentation formatting (table/json) with structured logs.
- [ ] Add CLI contract tests invoking fixture backend responses.

## Milestone 7 – `ragman` CLI (Plan step 7)
- [ ] Implement query command with confidence + citation rendering.
- [ ] Support `--json` output and latency reporting.
- [ ] Add no-answer path per FR-002 edge cases.

## Milestone 8 – Contract & integration testing (Plan step 8)
- [ ] Build Go/Python end-to-end test suites invoking both CLIs against backend.
- [ ] Add observability assertions (Phoenix trace presence, log format).
- [ ] Document test execution & coverage in handover notes.
