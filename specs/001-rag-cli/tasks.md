# Tasks: Local Linux RAG CLI

**Input**: Design documents from `/specs/001-rag-cli/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Every change MUST ship with pytest and Go coverage that fails before implementation; include contract, integration, unit, and observability smoke tests to satisfy constitution gates and TDD expectations.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

- **Architecture**: Maintain hexagonal boundaries with explicit ports/adapters before wiring transports.
- **Maintainability**: Keep modules focused; split classes into their own files as needed.
- **Simplicity**: Implement the minimum slice required for each story; defer optional enhancements.
- **Logging**: Instrument INFO/DEBUG statements using the mandated `ClassName.method(params) :: step` pattern without exposing sensitive data.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize repository structure, toolchains, and package scaffolding needed before any feature work.

- [ ] T001 Scaffold feature directories under `cli/ragman/`, `cli/ragadmin/`, `cli/shared/`, and `services/rag_backend/` to match the approved project structure.
- [ ] T002 Initialize the Go workspace linking CLI modules in `go.work` with relative paths to `cli/ragman`, `cli/ragadmin`, and `cli/shared`.
- [ ] T003 Create Go module metadata for `ragman` in `cli/ragman/go.mod` pinned to Go 1.23 with `github.com/spf13/cobra/v1` dependency.
- [ ] T004 Create Go module metadata for `ragadmin` in `cli/ragadmin/go.mod` pinned to Go 1.23 with `github.com/spf13/cobra/v1` dependency.
- [ ] T005 Create shared Go module metadata for IPC utilities in `cli/shared/go.mod` (Go 1.23) with replace directives for local CLI modules.
- [ ] T006 Bootstrap the Python backend package by adding `services/rag_backend/pyproject.toml` (uv managed) and `services/rag_backend/__init__.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Deliver shared transport, domain, adapter, and application scaffolding that all user stories depend on.

### Milestone 1 – IPC transport scaffold

- [ ] T007 [P] Author failing transport handshake contract tests in `tests/python/contract/test_transport_server.py`.
- [ ] T008 [P] Author failing Go IPC framing tests against `/v1/query` responses in `tests/go/contract/transport_client_test.go`.
- [ ] T009 Implement newline-delimited JSON Unix socket server skeleton with correlation IDs in `services/rag_backend/adapters/transport/server.py`.
- [ ] T010 Implement Go IPC framing client with validation and logging hooks in `cli/shared/ipc/client.go`.
- [ ] T011 Record Milestone 1 completion in `specs/001-rag-cli/milestones.md` once framing tests pass.

### Milestone 2 – Domain services & ports

- [ ] T012 [P] Add failing port interface tests for query, ingestion, and health flows in `tests/python/unit/ports/test_port_contracts.py`.
- [ ] T013 [P] Add failing domain service tests covering `KnowledgeSource`, `IngestionJob`, and `ContentIndexVersion` transitions in `tests/python/unit/domain/test_services.py`.
- [ ] T014 Define query, ingestion, and health port protocols in `services/rag_backend/ports/query.py`, `services/rag_backend/ports/ingestion.py`, and `services/rag_backend/ports/health.py`.
- [ ] T015 Implement domain services for retrieval, catalog management, and health evaluation in `services/rag_backend/domain/query_service.py`, `services/rag_backend/domain/source_service.py`, and `services/rag_backend/domain/health_service.py`.
- [ ] T016 Record Milestone 2 completion in `specs/001-rag-cli/milestones.md` after port and domain tests green.

### Milestone 3 – Infrastructure adapters

- [ ] T017 [P] Add failing integration tests for Weaviate and Ollama adapters with dynamic batching in `tests/python/integration/test_vector_adapters.py`.
- [ ] T018 [P] Add failing storage and audit logging tests safeguarding `SourceCatalog` persistence in `tests/python/unit/adapters/test_storage_adapter.py`.
- [ ] T019 [P] Add failing ingestion resume tests simulating mid-run failures in `tests/python/integration/test_ingestion_recovery.py`.
- [ ] T020 [P] Add failing corrupt source quarantine tests in `tests/python/unit/adapters/test_source_quarantine.py`.
- [ ] T021 Implement Weaviate and Ollama adapters with latency metrics in `services/rag_backend/adapters/weaviate/client.py` and `services/rag_backend/adapters/ollama/client.py`.
- [ ] T022 Implement catalog storage and audit logging adapters honoring XDG paths in `services/rag_backend/adapters/storage/catalog.py` and `services/rag_backend/adapters/storage/audit_log.py`.
- [ ] T023 Implement Phoenix/structlog instrumentation helpers in `services/rag_backend/adapters/observability/telemetry.py`.
- [ ] T024 Implement resumable ingestion recovery for interrupted jobs in `services/rag_backend/domain/job_recovery.py`.
- [ ] T025 Implement corrupt source quarantine workflow in `services/rag_backend/domain/source_service.py`.
- [ ] T026 Record Milestone 3 completion in `specs/001-rag-cli/milestones.md` after adapter and resilience tests succeed.

### Milestone 3A – Offline guarantee

- [ ] T027 [P] Add failing backend offline compliance tests that block outbound HTTP in `tests/python/integration/test_offline_guards.py`.
- [ ] T028 [P] Add failing CLI offline compliance tests covering `ragman` and `ragadmin` flows in `tests/go/contract/offline_guard_test.go`.
- [ ] T029 Implement backend offline enforcement and safe adapter wiring in `services/rag_backend/application/offline_guard.py`.
- [ ] T030 Implement shared Go IPC offline enforcement and structured logging in `cli/shared/ipc/client.go`.
- [ ] T031 Record offline milestone completion in `specs/001-rag-cli/milestones.md` once offline tests pass.

### Milestone 4 – Transport endpoints

- [ ] T032 [P] Add failing transport endpoint tests for `/v1/query`, `/v1/sources`, `/v1/index/reindex`, and `/v1/admin/*` in `tests/python/contract/test_transport_endpoints.py`.
- [ ] T033 [P] Add failing stale-index rejection tests for `/v1/query` in `tests/python/contract/test_transport_stale_index.py`.
- [ ] T034 Map port implementations to socket handlers with error semantics in `services/rag_backend/adapters/transport/handlers.py`.
- [ ] T035 Implement `/v1/admin/init` dependency verification and stale index handling in `services/rag_backend/adapters/transport/handlers.py`.
- [ ] T036 Record Milestone 4 completion in `specs/001-rag-cli/milestones.md` after endpoint tests pass.

### Milestone 5 – Shared Go IPC client

- [ ] T037 [P] Add failing Go unit tests for request builders and decoders in `tests/go/unit/ipc/client_test.go`.
- [ ] T038 Implement request builders, decoders, and retry/backoff logic in `cli/shared/ipc/client.go`.
- [ ] T039 Record Milestone 5 completion in `specs/001-rag-cli/milestones.md` once shared IPC tests are green.

---

## Phase 3: User Story 1 - Ask English Linux Questions via ragman (Priority: P1) 🎯 MVP

**Goal**: Enable operators to ask English questions via `ragman` and receive cited answers sourced from the local knowledge base.

**Independent Test**: Run `ragman "How do I change file permissions?"` against seeded sources and validate the English answer, at least one citation, and confidence output.

### Tests for User Story 1 (MANDATORY) ⚠️

- [ ] T040 [P] [US1] Add failing `ragman` CLI contract tests for success and no-answer flows in `tests/go/contract/ragman_query_test.go`.
- [ ] T041 [P] [US1] Add failing backend integration test asserting citation and confidence fields in `tests/python/integration/test_query_flow.py`.
- [ ] T042 [P] [US1] Add failing latency benchmark tests for SC-001 in `tests/python/performance/test_query_latency.py`.
- [ ] T043 [P] [US1] Add failing context-limit truncation tests in `tests/python/integration/test_context_limits.py`.

### Implementation for User Story 1

- [ ] T044 [US1] Implement query application orchestrator accumulating `QuerySession` telemetry in `services/rag_backend/application/query_runner.py`.
- [ ] T045 [US1] Instrument latency metrics and threshold enforcement in `services/rag_backend/application/query_metrics.py`.
- [ ] T046 [US1] Implement `ragman` root and query Cobra commands with flag validation in `cli/ragman/cmd/root.go` and `cli/ragman/cmd/query.go`.
- [ ] T047 [US1] Implement terminal and JSON renderers with citation/confidence formatting in `cli/ragman/internal/io/renderer.go`.
- [ ] T048 [US1] Handle context-limit messaging and truncation guidance in `cli/ragman/internal/io/renderer.go`.
- [ ] T049 [US1] Record Milestone 7 – `ragman` CLI completion in `specs/001-rag-cli/milestones.md` after CLI and backend tests pass.

---

## Phase 4: User Story 2 - Manage English Sources via ragadmin (Priority: P1)

**Goal**: Allow administrators to manage English knowledge sources, trigger reindexing, and keep the catalog current via `ragadmin`.

**Independent Test**: Execute `ragadmin sources list`, `ragadmin sources add <english zim>`, `ragadmin sources update <alias>`, `ragadmin sources remove <alias>`, and `ragadmin reindex`, confirming catalog updates and backend usage of new data.

### Tests for User Story 2 (MANDATORY) ⚠️

- [ ] T050 [P] [US2] Add failing `ragadmin` contract tests for listing and adding sources in `tests/go/contract/ragadmin_sources_list_add_test.go`.
- [ ] T051 [P] [US2] Add failing `ragadmin` contract tests for updating source metadata in `tests/go/contract/ragadmin_sources_update_test.go`.
- [ ] T052 [P] [US2] Add failing `ragadmin` contract tests for removing sources and verifying quarantine in `tests/go/contract/ragadmin_sources_remove_test.go`.
- [ ] T053 [P] [US2] Add failing backend integration tests for catalog lifecycle and alias collision handling in `tests/python/integration/test_source_catalog.py`.
- [ ] T054 [P] [US2] Add failing reindex performance tests for SC-002 in `tests/python/performance/test_reindex_duration.py`.

### Implementation for User Story 2

- [ ] T055 [US2] Implement source catalog service for list/add flows in `services/rag_backend/application/source_catalog.py`.
- [ ] T056 [US2] Implement source update workflows enforcing metadata validation in `services/rag_backend/application/source_catalog.py`.
- [ ] T057 [US2] Implement source removal and quarantine flows in `services/rag_backend/application/source_catalog.py`.
- [ ] T058 [US2] Implement `ragadmin reindex` command with progress feedback and timing output in `cli/ragadmin/cmd/reindex.go`.
- [ ] T059 [US2] Wire audit logging and language validation for source mutations in `services/rag_backend/adapters/storage/audit_log.py`.
- [ ] T060 [US2] Record Milestone 6 – `ragadmin` CLI completion in `specs/001-rag-cli/milestones.md` after catalog and CLI tests pass.

---

## Phase 5: User Story 3 - Local Setup and Health Visibility (Priority: P2)

**Goal**: Provide operators with deterministic init and health checks that validate prerequisites and system status before use.

**Independent Test**: On a clean machine, run `ragadmin init` then `ragadmin health`, verifying directory creation, dependency readiness, pass/fail indicators for index freshness, source accessibility, disk capacity, and offline compliance.

### Tests for User Story 3 (MANDATORY) ⚠️

- [ ] T061 [P] [US3] Add failing integration tests for init bootstrapping and health diagnostics in `tests/python/integration/test_init_health.py`.
- [ ] T062 [P] [US3] Add failing `ragadmin` contract tests for init and health output formats in `tests/go/contract/ragadmin_health_test.go`.
- [ ] T063 [P] [US3] Add failing disk capacity threshold tests in `tests/python/integration/test_disk_capacity.py`.
- [ ] T064 [P] [US3] Add failing missing or corrupt source detection tests in `tests/python/integration/test_source_health_failures.py`.

### Implementation for User Story 3

- [ ] T065 [US3] Implement init orchestration verifying Ollama/Weaviate readiness and seeding sources in `services/rag_backend/application/init_service.py`.
- [ ] T066 [US3] Implement health evaluation aggregator producing remediation guidance and disk checks in `services/rag_backend/application/health_service.py`.
- [ ] T067 [US3] Implement `ragadmin init` and `ragadmin health` Cobra commands with structured logging in `cli/ragadmin/cmd/init.go` and `cli/ragadmin/cmd/health.go`.
- [ ] T068 [US3] Persist init and health audit entries with trace IDs in `services/rag_backend/adapters/storage/audit_log.py`.

---

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: Harden observability, documentation, offline validation, and integration coverage across stories before release.

- [ ] T069 [P] Add end-to-end CLI↔backend contract suite covering FR-001–FR-011 in `tests/python/contract/test_end_to_end.py`.
- [ ] T070 [P] Add observability assertions for Phoenix traces and structured logs in `tests/python/integration/test_observability.py`.
- [ ] T071 Record Milestone 8 – Contract & integration testing completion in `specs/001-rag-cli/milestones.md`.
- [ ] T072 Run offline validation suite with network access disabled in `tests/system/test_offline_validation.sh`.
- [ ] T073 Run performance validation suite confirming SC-001 and SC-002 in `tests/system/test_performance_validation.py`.
- [ ] T074 Update CLI usage guides with new workflows in `docs/guides/cli/ragman.md` and `docs/guides/cli/ragadmin.md`.
- [ ] T075 Update Unix socket ADR with finalized port mappings in `docs/adr/0001-unix-socket-ipc.md`.
- [ ] T076 Document Quickstart validation results and troubleshooting notes in `specs/001-rag-cli/quickstart.md`.

---

## Dependencies & Execution Order

- **Story sequencing**: Complete Phase 2 (Foundational) before starting user stories; then deliver User Story 1 (US1) → User Story 2 (US2) → User Story 3 (US3) to align with MVP-first delivery while respecting milestone readiness.
- **Transport dependency**: T034–T039 must pass before any CLI command wiring (T046, T058, T067) to guarantee socket contract stability.
- **Catalog dependency**: T055–T059 must complete before T066 and T067 to ensure health commands read accurate source metadata.
- **Observability & offline dependency**: T023, T027–T031, and T070–T072 must complete before final validation so telemetry and offline guarantees are enforceable.

---

## Parallel Execution Examples

- **US1**: Run T040 and T041 in parallel to build failing Go and Python tests, then split T046 (command wiring) and T047/T048 (rendering and truncation) between contributors once T044–T045 land.
- **US2**: Execute T050–T052 concurrently; after T055, parallelize T056/T057 (update/remove flows) with T059 (audit logging) since they touch separate files.
- **US3**: Develop T061–T064 together, then implement T065 and T066 in parallel before integrating CLI commands in T067.

---

## Implementation Strategy

1. Finish Phases 1–2 to establish transport, domain, adapters, offline guards, and shared IPC utilities.
2. Deliver User Story 1 end-to-end as the MVP, validating query UX, latency instrumentation, and context-limit handling.
3. Layer User Story 2 to keep the knowledge base maintainable, including full CRUD coverage and reindex performance metrics, then User Story 3 for setup, health, and disk/availability diagnostics.
4. Close with the polish phase to strengthen observability, offline validation, performance benchmarks, and documentation before release.
