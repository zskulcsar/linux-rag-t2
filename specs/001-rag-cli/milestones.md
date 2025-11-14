# Tasks: Local Linux RAG CLI

## Milestone 1 – IPC transport scaffold (Plan step 1)
- [X] Implement backend Unix socket server skeleton (`backend/src/adapters/transport/server.py`) using contract schema.
- [X] Implement Go IPC client framing utilities (`cli/shared/ipc/client.go`).
- [X] Add request/response validation tests referencing `contracts/backend-openapi.yaml`.

## Milestone 2 – Domain services & ports (Plan step 2)
- [X] Define query, ingestion, health ports in `backend/src/ports/`.
- [X] Implement domain services in `backend/src/domain/` covering FR-001–FR-011.
- [X] Author unit tests for domain logic (pytest + mypy strict).

## Milestone 3 – Infrastructure adapters (Plan step 3)
- [X] Create Weaviate adapter (ingest/query) with dynamic batching per `research.md`.
- [X] Create Ollama adapter for embedding + generation with latency metrics.
- [X] Implement catalog storage and audit logging adapters honoring XDG paths.
- [X] Wire Phoenix instrumentation (`arize-phoenix`) and structured logging.

## Milestone 3A – Offline guarantee (Plan step 4 enforcement)
- [X] Add backend offline compliance tests (`tests/python/integration/test_offline_guards.py`) covering blocked remote sockets and loopback allowances.
- [X] Add CLI offline compliance tests (`tests/go/contract/offline_guard_test.go`) asserting outbound HTTP blocking and loopback success.
- [X] Implement backend offline guard (`backend/src/application/offline_guard.py`) enforcing FR-010.
- [X] Implement shared Go IPC offline guard (`cli/shared/ipc/client.go`) with structured logging and error propagation.
- [X] Execute offline guard suites (`uv run pytest tests/python/integration/test_offline_guards.py`, `go test ./tests/go/contract -run OfflineGuard`) confirming all checks pass.

## Milestone 4 – Transport endpoints (Plan step 4)
- [X] Map domain ports to `/v1/*` handlers in transport adapter with error semantics.
- [X] Add init verification path covering FR-005 (Weaviate + Ollama checks).
- [X] Extend contract tests to cover stale index and init failure flows.
- [X] Execute transport endpoint suites (`uv run pytest tests/python/contract/test_transport_endpoints.py tests/python/contract/test_transport_stale_index.py`) confirming green tests before documenting completion.

## Milestone 5 – Shared Go IPC client (Plan step 5)
- [X] Implement request builders and response decoders shared by CLIs.
- [X] Cover with Go unit tests mirroring backend contract validation; evaluate need for retry/backoff after baseline flows are validated.
- [X] Execute shared IPC suites (`GOCACHE=$(pwd)/.gocache go test ./tests/go/unit/ipc ./tests/go/contract`) confirming green results before documenting completion.

## Milestone 6 – `ragadmin` CLI (Plan step 6)
- [ ] Scaffold Cobra root and subcommands (init, sources, reindex, health).
- [ ] Implement presentation formatting (table/json) with structured logs.
- [ ] Add CLI contract tests invoking fixture backend responses.

## Milestone 7 – `ragman` CLI (Plan step 7)
- [X] Implement query command with confidence + citation rendering.
- [X] Support `--json` output and latency reporting.
- [X] Add no-answer path per FR-002 edge cases.
- [X] Execute CLI/backend verification suites (`GOCACHE=$(pwd)/../.gocache go test ./unit/ragman`, `UV_CACHE_DIR=$(pwd)/.uv-cache uv run pytest tests/python/unit -k query`) confirming green results.

## Milestone 8 – Contract & integration testing (Plan step 8)
- [ ] Build Go/Python end-to-end test suites invoking both CLIs against backend.
- [ ] Add observability assertions (Phoenix trace presence, log format).
- [ ] Document test execution & coverage in handover notes.
