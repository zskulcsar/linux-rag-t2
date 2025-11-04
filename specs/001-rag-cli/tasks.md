# Tasks: Local Linux RAG CLI

**Input**: Design documents from `/specs/001-rag-cli/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Every change MUST ship with pytest and Go coverage that fails before implementation; include contract, integration, unit, and observability smoke tests to satisfy constitution gates and TDD expectations.

**Organization**: Tasks are grouped by phase and user story to enable independent implementation and testing of each story.

- **Architecture**: Maintain hexagonal boundaries; define explicit ports/adapters before wiring transports.
- **Maintainability**: Keep modules focused; split features into dedicated files when responsibilities diverge.
- **Simplicity**: Implement only the scope needed for each story; defer optional enhancements.
- **Logging**: Instrument INFO/DEBUG statements using the mandated `ClassName.method(params) :: step` pattern without exposing sensitive data.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize repository structure, toolchains, and package scaffolding needed before any feature work.

- [X] T001 Scaffold feature directories under `cli/ragman/`, `cli/ragadmin/`, `cli/shared/`, and `services/rag_backend/` per the approved project structure.
- [X] T002 Initialize the Go workspace, linking CLI modules in `go.work` with relative paths to `cli/ragman`, `cli/ragadmin`, and `cli/shared`.
- [X] T003 Create Go module metadata for `ragman` in `cli/ragman/go.mod` pinned to Go 1.23 with `github.com/spf13/cobra/v1` dependency.
- [X] T004 Create Go module metadata for `ragadmin` in `cli/ragadmin/go.mod` pinned to Go 1.23 with `github.com/spf13/cobra/v1` dependency.
- [X] T005 Create shared Go module metadata for IPC utilities in `cli/shared/go.mod` with replace directives for local CLI modules.
- [X] T006 Bootstrap the Python backend package by adding `services/rag_backend/pyproject.toml` (uv managed) and `services/rag_backend/__init__.py`.
- [X] T007 Create language-specific test scaffolding under `tests/go/{unit,contract}/` and `tests/python/{unit,integration,contract,performance}/`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Deliver shared transport, domain, adapter, resilience, and offline infrastructure that all user stories depend on.

### Milestone 1 – IPC transport scaffold

- [X] T008 [P] Author failing transport handshake contract tests in `tests/python/contract/test_transport_server.py`.
- [X] T009 [P] Author failing Go IPC framing tests for `/v1/query` in `tests/go/contract/transport_client_test.go`.
- [X] T010 Implement newline-delimited JSON Unix socket server skeleton with correlation IDs in `services/rag_backend/adapters/transport/server.py`.
- [X] T011 Implement Go IPC client framing with validation and logging hooks in `cli/shared/ipc/client.go`.
- [X] T012 Record Milestone 1 completion in `specs/001-rag-cli/milestones.md` once handshake tests pass.

### Milestone 2 – Domain services & ports

- [X] T013 [P] Add failing port interface tests for query, ingestion, and health flows in `tests/python/unit/ports/test_port_contracts.py`.
- [X] T014 [P] Add failing domain service tests covering `KnowledgeSource`, `IngestionJob`, and `ContentIndexVersion` transitions in `tests/python/unit/domain/test_services.py`.
- [X] T015 Define query, ingestion, and health port protocols in `services/rag_backend/ports/query.py`, `services/rag_backend/ports/ingestion.py`, and `services/rag_backend/ports/health.py`.
- [X] T016 Implement domain services covering retrieval, catalog management, and health evaluation in `services/rag_backend/domain/query_service.py`, `services/rag_backend/domain/source_service.py`, and `services/rag_backend/domain/health_service.py`.
- [X] T017 Record Milestone 2 completion in `specs/001-rag-cli/milestones.md` after port and domain tests succeed.

### Milestone 3 – Infrastructure adapters & resilience

- [X] T018 [P] Add failing integration tests for Weaviate and Ollama adapters with dynamic batching in `tests/python/integration/test_vector_adapters.py`. Verify the fixtures assert alias/type/language metadata round-trips and capture per-alias ingestion metrics.
- [X] T019 [P] Add failing storage and audit logging tests safeguarding the `SourceCatalog` persistence in `tests/python/unit/adapters/test_storage_adapter.py`.
- [X] T020 [P] Add failing ingestion resume tests simulating mid-run failures in `tests/python/integration/test_ingestion_recovery.py`.
- [X] T021 [P] Add failing corrupt source quarantine tests in `tests/python/unit/adapters/test_source_quarantine.py`.
- [X] T022 Implement Weaviate and Ollama adapters with latency metrics in `services/rag_backend/adapters/weaviate/client.py` and `services/rag_backend/adapters/ollama/client.py`. Implement the Weaviate adapter around a single `Document` class with deterministic IDs (`<alias>:<checksum>:<chunk_id>`), required alias/type/language filters, and structured logs/metrics for per-alias ingestion and query latency.
- [X] T023 Implement catalog storage and audit logging adapters honoring XDG paths in `services/rag_backend/adapters/storage/catalog.py` and `services/rag_backend/adapters/storage/audit_log.py`.
- [X] T024 Implement Phoenix/structlog instrumentation helpers in `services/rag_backend/adapters/observability/telemetry.py`.
- [X] T025 Implement resumable ingestion recovery for interrupted jobs in `services/rag_backend/domain/job_recovery.py`.
- [X] T026 Implement corrupt source quarantine workflow updates in `services/rag_backend/domain/source_service.py`.
- [X] T027 Record Milestone 3 completion in `specs/001-rag-cli/milestones.md` after adapter and resilience tests pass.

### Milestone 3A – Offline guarantee

- [X] T028 [P] Add failing backend offline compliance tests that block outbound HTTP in `tests/python/integration/test_offline_guards.py`.
- [X] T029 [P] Add failing CLI offline compliance tests covering `ragman` and `ragadmin` flows in `tests/go/contract/offline_guard_test.go`.
- [X] T030 Implement backend offline enforcement and safe adapter guards in `services/rag_backend/application/offline_guard.py`.
- [X] T031 Implement shared Go IPC offline enforcement and structured logging in `cli/shared/ipc/client.go`.
- [X] T032 Record offline milestone completion in `specs/001-rag-cli/milestones.md` after offline test pass.

### Milestone 4 – Transport endpoints

- [X] T033 [P] Add failing transport endpoint tests for `/v1/query`, `/v1/sources`, `/v1/index/reindex`, and `/v1/admin/*` in `tests/python/contract/test_transport_endpoints.py`.
- [X] T034 [P] Add failing stale-index rejection tests for `/v1/query` returning 409 in `tests/python/contract/test_transport_stale_index.py`.
- [X] T035 Map domain ports to socket handlers with standardized errors in `services/rag_backend/adapters/transport/handlers.py`.
- [X] T036 Implement `/v1/admin/init` verification and stale-index rejection logic in `services/rag_backend/adapters/transport/handlers.py`.
- [ ] T037 Record Milestone 4 completion in `specs/001-rag-cli/milestones.md` after endpoint tests pass.

### Milestone 5 – Shared Go IPC client

- [ ] T038 [P] Add failing Go unit tests for request builders and decoders in `tests/go/unit/ipc/client_test.go`.
- [ ] T039 Implement request builders, decoders, and retry/backoff logic in `cli/shared/ipc/client.go`.
- [ ] T040 Record Milestone 5 completion in `specs/001-rag-cli/milestones.md` once shared IPC tests turn green.

---

## Phase 3: User Story 1 - Ask English Linux Questions via ragman (Priority: P1) 🎯 MVP

**Goal**: Enable operators to ask English questions via `ragman` and receive cited answers sourced from the local knowledge base.

**Independent Test**: Run `ragman "How do I change file permissions?"` against seeded sources and validate the English answer, at least one citation, and confidence output.

### Tests for User Story 1 (MANDATORY) ⚠️

- [ ] T041 [P] [US1] Add failing `ragman` CLI contract tests for success and no-answer paths in `tests/go/contract/ragman_query_test.go`. Extend cases to cover the 0.35 confidence threshold, stale-index fallbacks, structured `summary`/`steps`/`references` fields, raw JSON output (`--json`), citation marker reuse for repeated `{alias, document_ref}` pairs, and correlation ID propagation in logs. Include assertions for `--plain` mode to ensure sections and inline citations mirror the markdown output (FR-002).
- [ ] T042 [P] [US1] Add failing backend integration test asserting `summary`, ordered `steps`, `references`, semantic chunk counts (≤2 000 tokens), citation and confidence fields in `tests/python/integration/test_query_flow.py`.
- [ ] T043 [P] [US1] Add failing latency benchmark tests for SC-001 in `tests/python/performance/test_query_latency.py`.
- [ ] T044 [P] [US1] Add failing context-limit truncation tests in `tests/python/integration/test_context_limits.py`.

### Implementation for User Story 1

- [ ] T045 [US1] Implement query application orchestrator with telemetry in `services/rag_backend/application/query_runner.py`. Load the minimum confidence from presentation config and pass the effective threshold into responses.
- [ ] T046 [US1] Instrument latency metrics and thresholds in `services/rag_backend/application/query_metrics.py`.
- [ ] T047 [US1] Implement `ragman` root and query spf13/cobra commands in `cli/ragman/cmd/root.go` and `cli/ragman/cmd/query.go`. Commands must emit correlation IDs and request the structured answer format over the IPC client. Expose `--plain`, `--json`, `--context-tokens`, and `--conversation` flags.
- [ ] T048 [US1] Implement terminal/JSON renderers with citation, confidence, and truncation messaging in `cli/ragman/internal/io/renderer.go`. Render Summary, Steps, and References sections with inline aliases and fall back to the standard “No answer found” block when confidence < 0.35. Provide markdown, plain, and JSON presenters via templates that display confidence as a percentage header and honour `${XDG_CONFIG_HOME}/ragcli/config.yaml` defaults.
- [ ] T049 [US1] Record Milestone 7 completion in `specs/001-rag-cli/milestones.md` after CLI and backend tests pass.

---

## Phase 4: User Story 2 - Manage English Sources via ragadmin (Priority: P1)

**Goal**: Allow administrators to manage English knowledge sources, including CRUD operations, reindexing, audit logging, and keep the catalog current via `ragadmin`.

**Independent Test**: Run `ragadmin sources list`, `ragadmin sources add <path>`, `ragadmin sources update <alias>`, `ragadmin sources remove <alias>`, and `ragadmin reindex`; confirming catalog updates and backend usage of new data.

### Tests for User Story 2 (MANDATORY) ⚠️

- [ ] T050 [P] [US2] Add failing `ragadmin` contract tests for listing and adding sources in `tests/go/contract/ragadmin_sources_list_add_test.go`.
- [ ] T051 [P] [US2] Add failing `ragadmin` contract tests for updating source metadata in `tests/go/contract/ragadmin_sources_update_test.go`, verifying that updates can mutate metadata fields aside from alias and that alias changes require remove-and-add flows (FR-003, FR-006).
- [ ] T052 [P] [US2] Add failing `ragadmin` contract tests for removing sources and verifying quarantine in `tests/go/contract/ragadmin_sources_remove_test.go`.
- [ ] T053 [P] [US2] Add failing backend integration tests for catalog lifecycle, SHA256 checksum persistence, deterministic `<alias>:<checksum>:<chunk_id>` document IDs, and alias collision handling in `tests/python/integration/test_source_catalog.py`.
- [ ] T054 [P] [US2] Add failing reindex performance tests for SC-002 in `tests/python/performance/test_reindex_duration.py`.

### Implementation for User Story 2

- [ ] T055 [US2] Implement source catalog service for list/add flows with validation in `services/rag_backend/application/source_catalog.py`.
- [ ] T056 [US2] Implement source update workflows enforcing metadata validation in `services/rag_backend/application/source_catalog.py`.
- [ ] T057 [US2] Implement source removal and quarantine flows in `services/rag_backend/application/source_catalog.py`.
- [ ] T058 [US2] Implement `ragadmin` sources spf13/cobra commands with table/JSON output in `cli/ragadmin/cmd/sources.go`, writing audit log entries as JSON lines.
- [ ] T059 [US2] Implement `ragadmin reindex` spf13/cobra command with progress feedback (stage plus optional percent) and timing output in `cli/ragadmin/cmd/reindex.go`.
- [ ] T060 [US2] Wire audit logging and language validation for mutations in `services/rag_backend/adapters/storage/audit_log.py`.
- [ ] T061 [US2] Record Milestone 6 completion in `specs/001-rag-cli/milestones.md` after CRUD tests pass.

---

## Phase 5: User Story 3 - Local Setup and Health Visibility (Priority: P2)

**Goal**: Provide operators with deterministic init and health checks that validate prerequisites and system status before use.

**Independent Test**: On a clean machine, run `ragadmin init` then `ragadmin health`, verifying directory creation, dependency readiness, pass/fail indicators for index freshness, source accessibility, disk capacity, and offline compliance.

### Tests for User Story 3 (MANDATORY) ⚠️

- [ ] T062 [P] [US3] Add failing integration tests for init bootstrapping and health diagnostics in `tests/python/integration/test_init_health.py`.
- [ ] T063 [P] [US3] Add failing `ragadmin` contract tests for init and health output in `tests/go/contract/ragadmin_health_test.go`, covering disk free thresholds, 30-day index freshness, exponential retry/backoff, and minimal remediation strings.
- [ ] T064 [P] [US3] Add failing disk capacity threshold tests in `tests/python/integration/test_disk_capacity.py`.
- [ ] T065 [P] [US3] Add failing missing or corrupt source detection tests in `tests/python/integration/test_source_health_failures.py`.

### Implementation for User Story 3

- [ ] T066 [US3] Implement init orchestration verifying Ollama/Weaviate readiness and seeding sources in `services/rag_backend/application/init_service.py`. Seed the presentation config file with the default minimum confidence when it is missing and register default `man-pages`/`info-pages` entries.
- [ ] T067 [US3] Implement health evaluation aggregator producing remediation guidance and disk checks in `services/rag_backend/application/health_service.py`.
- [ ] T068 [US3] Implement `ragadmin init` and `ragadmin health` spf13/cobra commands with structured logging in `cli/ragadmin/cmd/init.go` and `cli/ragadmin/cmd/health.go`, delegating threshold logic to dedicated helpers and ensuring `${XDG_DATA_HOME}/ragcli/kiwix/` exists.
- [ ] T069 [US3] Persist init and health audit entries with trace IDs in `services/rag_backend/adapters/storage/audit_log.py`.

---

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: Finalize observability, offline/performance validation, documentation, and integration coverage across stories ahead of release.

- [ ] T070 [P] Add end-to-end CLI↔backend contract suite covering FR-001–FR-011 in `tests/python/contract/test_end_to_end.py`.
- [ ] T071 [P] Add observability assertions for Phoenix traces and structured logs in `tests/python/integration/test_observability.py`.
- [ ] T072 Record Milestone 8 completion in `specs/001-rag-cli/milestones.md` after end-to-end suites pass.
- [ ] T073 Run offline validation suite with network-disabled runs in `tests/system/test_offline_validation.sh`.
- [ ] T074 Run performance validation suite confirming SC-001 and SC-002 in `tests/system/test_performance_validation.py`.
- [ ] T075 Update ragman CLI usage guide with new workflows in `docs/guides/cli/ragman.md`.
- [ ] T076 Update ragadmin CLI usage guide with new workflows in `docs/guides/cli/ragadmin.md`.
- [ ] T077 Update Unix socket ADR with finalized port mappings in `docs/adr/0001-unix-socket-ipc.md`.
- [ ] T078 Document Quickstart validation results and troubleshooting notes in `specs/001-rag-cli/quickstart.md`.
- [ ] T079 Add failing Go unit tests for audit log JSON writer and config loader helpers in `tests/go/unit/system_defaults_test.go`.
- [ ] T080 Add failing Go unit tests for health retry/backoff utilities in `tests/go/unit/health_retry_test.go`.
- [ ] T081 [P] Add failing accuracy evaluation harness covering SC-001 in `tests/system/test_accuracy_eval.py`. Define a labeled corpus of representative queries with expected summaries, invoke `ragman query` through the CLI contract harness, compare structured responses against the ground truth, and assert the run achieves ≥90 % accuracy while capturing detailed mismatch diagnostics for remediation.

---

## Dependencies & Execution Order

- **Story sequencing**: Complete Phases 1–2 first, then deliver User Story 1 (US1) → User Story 2 (US2) → User Story 3 (US3) to align with MVP-first delivery while respecting milestone readiness.
- **Transport dependency**: T033–T040 must pass before wiring CLI commands (T047, T058, T068) to guarantee contract-stable transports.
- **Catalog dependency**: T055–T057 must complete before health orchestration (T067) to ensure accurate metadata.
- **Observability & offline dependency**: T024, T028–T032, and T070–T074 must succeed prior to final validation to satisfy constitution mandates and that telemetry and offline guarantees are enforceable.

---

## Parallel Execution Examples

- **US1**: Run T041–T044 in parallel to seed failing tests, then split T047 (command wiring) and T048 (rendering/truncation) after T045–T046 land.
- **US2**: Execute T050–T052 concurrently; after T055, parallelize T056/T057 (update/remove flows) with T059 (reindex UX) since they touch distinct files.
- **US3**: Develop T062–T065 together, then implement T066 and T067 in parallel before integrating CLI commands in T068.

---

## Implementation Strategy

1. Complete Phases 1–2 to lock down transport, domain, adapters, resilience, and offline safeguards and shared IPC utilities.
2. Deliver User Story 1 end-to-end as the MVP, validating latency instrumentation and context-limit handling.
3. Layer User Story 2 to keep the knowledge base maintainable, including full CRUD coverage and reindex performance metrics, then User Story 3 for setup, health, and disk/availability diagnostics.
4. Finish with the polish phase to strengthen observability, offline guarantees, performance benchmarks, and documentation updates.
