import Std

namespace Specs001RagCli

open Std

inductive Phase
  | setup
  | foundational
  | userStory1
  | userStory2
  | userStory3
  | polish
  deriving Repr, DecidableEq, Inhabited

inductive TaskStatus
  | todo
  | inProgress
  | done
  | blocked
  deriving Repr, DecidableEq, Inhabited

structure Task where
  id : String
  title : String
  phase : Phase
  stage : String
  description : String
  files : List String
  parallel : Bool
  dependencies : List String
  status : TaskStatus := TaskStatus.todo
  notes : List String := []
  deriving Repr, DecidableEq

def setupTasks : List Task :=
  [
    { id := "T001",
      title := "Scaffold feature directories under `cli/ragman/`, `cli/ragadmin/`, `cli/shared/`, and `services/rag_backend/` per the...",
      phase := Phase.setup,
      stage := "Phase 1 - Setup",
      description := "Scaffold feature directories under `cli/ragman/`, `cli/ragadmin/`, `cli/shared/`, and `services/rag_backend/` per the approved project structure.",
      files := ["cli/ragman/", "cli/ragadmin/", "cli/shared/", "services/rag_backend/"],
      parallel := false,
      dependencies := []
    },
    { id := "T002",
      title := "Initialize the Go workspace, linking CLI modules",
      phase := Phase.setup,
      stage := "Phase 1 - Setup",
      description := "Initialize the Go workspace, linking CLI modules in `go.work` with relative paths to `cli/ragman`, `cli/ragadmin`, and `cli/shared`.",
      files := ["go.work", "cli/ragman", "cli/ragadmin", "cli/shared"],
      parallel := false,
      dependencies := ["T001"]
    },
    { id := "T003",
      title := "Create Go module metadata for `ragman`",
      phase := Phase.setup,
      stage := "Phase 1 - Setup",
      description := "Create Go module metadata for `ragman` in `cli/ragman/go.mod` pinned to Go 1.23 with `github.com/spf13/cobra/v1` dependency.",
      files := ["ragman", "cli/ragman/go.mod", "github.com/spf13/cobra/v1"],
      parallel := false,
      dependencies := ["T001", "T002"]
    },
    { id := "T004",
      title := "Create Go module metadata for `ragadmin`",
      phase := Phase.setup,
      stage := "Phase 1 - Setup",
      description := "Create Go module metadata for `ragadmin` in `cli/ragadmin/go.mod` pinned to Go 1.23 with `github.com/spf13/cobra/v1` dependency.",
      files := ["ragadmin", "cli/ragadmin/go.mod", "github.com/spf13/cobra/v1"],
      parallel := false,
      dependencies := ["T001", "T002"]
    },
    { id := "T005",
      title := "Create shared Go module metadata for IPC utilities",
      phase := Phase.setup,
      stage := "Phase 1 - Setup",
      description := "Create shared Go module metadata for IPC utilities in `cli/shared/go.mod` with replace directives for local CLI modules.",
      files := ["cli/shared/go.mod"],
      parallel := false,
      dependencies := ["T001", "T002"]
    },
    { id := "T006",
      title := "Bootstrap the Python backend package by adding `services/rag_backend/pyproject.toml` (uv managed) and `services/rag_b...",
      phase := Phase.setup,
      stage := "Phase 1 - Setup",
      description := "Bootstrap the Python backend package by adding `services/rag_backend/pyproject.toml` (uv managed) and `services/rag_backend/__init__.py`.",
      files := ["services/rag_backend/pyproject.toml", "services/rag_backend/__init__.py"],
      parallel := false,
      dependencies := ["T001"]
    },
    { id := "T007",
      title := "Create language-specific test scaffolding under `tests/go/{unit,contract}/` and `tests/python/{unit,integration,contr...",
      phase := Phase.setup,
      stage := "Phase 1 - Setup",
      description := "Create language-specific test scaffolding under `tests/go/{unit,contract}/` and `tests/python/{unit,integration,contract,performance}/`.",
      files := ["tests/go/{unit,contract}/", "tests/python/{unit,integration,contract,performance}/"],
      parallel := false,
      dependencies := ["T001"]
    }
  ]

def foundationalTasks : List Task :=
  [
    { id := "T008",
      title := "Author failing transport handshake contract tests",
      phase := Phase.foundational,
      stage := "Milestone 1 - IPC transport scaffold",
      description := "Author failing transport handshake contract tests in `tests/python/contract/test_transport_server.py`.",
      files := ["tests/python/contract/test_transport_server.py"],
      parallel := true,
      dependencies := ["T007"]
    },
    { id := "T009",
      title := "Author failing Go IPC framing tests for `/v1/query`",
      phase := Phase.foundational,
      stage := "Milestone 1 - IPC transport scaffold",
      description := "Author failing Go IPC framing tests for `/v1/query` in `tests/go/contract/transport_client_test.go`.",
      files := ["/v1/query", "tests/go/contract/transport_client_test.go"],
      parallel := true,
      dependencies := ["T007"]
    },
    { id := "T010",
      title := "Implement newline-delimited JSON Unix socket server skeleton with correlation IDs",
      phase := Phase.foundational,
      stage := "Milestone 1 - IPC transport scaffold",
      description := "Implement newline-delimited JSON Unix socket server skeleton with correlation IDs in `services/rag_backend/adapters/transport/server.py`.",
      files := ["services/rag_backend/adapters/transport/server.py"],
      parallel := false,
      dependencies := ["T008", "T009"]
    },
    { id := "T011",
      title := "Implement Go IPC client framing with validation and logging hooks",
      phase := Phase.foundational,
      stage := "Milestone 1 - IPC transport scaffold",
      description := "Implement Go IPC client framing with validation and logging hooks in `cli/shared/ipc/client.go`.",
      files := ["cli/shared/ipc/client.go"],
      parallel := false,
      dependencies := ["T008", "T009"]
    },
    { id := "T012",
      title := "Record Milestone 1 completion",
      phase := Phase.foundational,
      stage := "Milestone 1 - IPC transport scaffold",
      description := "Record Milestone 1 completion in `specs/001-rag-cli/milestones.md` once handshake tests pass.",
      files := ["specs/001-rag-cli/milestones.md"],
      parallel := false,
      dependencies := ["T010", "T011"]
    },
    { id := "T013",
      title := "Add failing port interface tests for query, ingestion, and health flows",
      phase := Phase.foundational,
      stage := "Milestone 2 - Domain services & ports",
      description := "Add failing port interface tests for query, ingestion, and health flows in `tests/python/unit/ports/test_port_contracts.py`.",
      files := ["tests/python/unit/ports/test_port_contracts.py"],
      parallel := true,
      dependencies := ["T012"]
    },
    { id := "T014",
      title := "Add failing domain service tests covering `KnowledgeSource`, `IngestionJob`, and `ContentIndexVersion` transitions",
      phase := Phase.foundational,
      stage := "Milestone 2 - Domain services & ports",
      description := "Add failing domain service tests covering `KnowledgeSource`, `IngestionJob`, and `ContentIndexVersion` transitions in `tests/python/unit/domain/test_services.py`.",
      files := ["KnowledgeSource", "IngestionJob", "ContentIndexVersion", "tests/python/unit/domain/test_services.py"],
      parallel := true,
      dependencies := ["T012"]
    },
    { id := "T015",
      title := "Define query, ingestion, and health port protocols",
      phase := Phase.foundational,
      stage := "Milestone 2 - Domain services & ports",
      description := "Define query, ingestion, and health port protocols in `services/rag_backend/ports/query.py`, `services/rag_backend/ports/ingestion.py`, and `services/rag_backend/ports/health.py`.",
      files := ["services/rag_backend/ports/query.py", "services/rag_backend/ports/ingestion.py", "services/rag_backend/ports/health.py"],
      parallel := false,
      dependencies := ["T013", "T014"]
    },
    { id := "T016",
      title := "Implement domain services covering retrieval, catalog management, and health evaluation",
      phase := Phase.foundational,
      stage := "Milestone 2 - Domain services & ports",
      description := "Implement domain services covering retrieval, catalog management, and health evaluation in `services/rag_backend/domain/query_service.py`, `services/rag_backend/domain/source_service.py`, and `services/rag_backend/domain/health_service.py`.",
      files := ["services/rag_backend/domain/query_service.py", "services/rag_backend/domain/source_service.py", "services/rag_backend/domain/health_service.py"],
      parallel := false,
      dependencies := ["T015"]
    },
    { id := "T017",
      title := "Record Milestone 2 completion",
      phase := Phase.foundational,
      stage := "Milestone 2 - Domain services & ports",
      description := "Record Milestone 2 completion in `specs/001-rag-cli/milestones.md` after port and domain tests succeed.",
      files := ["specs/001-rag-cli/milestones.md"],
      parallel := false,
      dependencies := ["T015", "T016"]
    },
    { id := "T018",
      title := "Add failing integration tests for Weaviate and Ollama adapters with dynamic batching",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Add failing integration tests for Weaviate and Ollama adapters with dynamic batching in `tests/python/integration/test_vector_adapters.py`.",
      files := ["tests/python/integration/test_vector_adapters.py"],
      parallel := true,
      dependencies := ["T017"]
    },
    { id := "T019",
      title := "Add failing storage and audit logging tests safeguarding the `SourceCatalog` persistence",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Add failing storage and audit logging tests safeguarding the `SourceCatalog` persistence in `tests/python/unit/adapters/test_storage_adapter.py`.",
      files := ["SourceCatalog", "tests/python/unit/adapters/test_storage_adapter.py"],
      parallel := true,
      dependencies := ["T017"]
    },
    { id := "T020",
      title := "Add failing ingestion resume tests simulating mid-run failures",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Add failing ingestion resume tests simulating mid-run failures in `tests/python/integration/test_ingestion_recovery.py`.",
      files := ["tests/python/integration/test_ingestion_recovery.py"],
      parallel := true,
      dependencies := ["T017"]
    },
    { id := "T021",
      title := "Add failing corrupt source quarantine tests",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Add failing corrupt source quarantine tests in `tests/python/unit/adapters/test_source_quarantine.py`.",
      files := ["tests/python/unit/adapters/test_source_quarantine.py"],
      parallel := true,
      dependencies := ["T017"]
    },
    { id := "T022",
      title := "Implement Weaviate and Ollama adapters with latency metrics",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Implement Weaviate and Ollama adapters with latency metrics in `services/rag_backend/adapters/weaviate/client.py` and `services/rag_backend/adapters/ollama/client.py`.",
      files := ["services/rag_backend/adapters/weaviate/client.py", "services/rag_backend/adapters/ollama/client.py"],
      parallel := false,
      dependencies := ["T018"]
    },
    { id := "T023",
      title := "Implement catalog storage and audit logging adapters honoring XDG paths",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Implement catalog storage and audit logging adapters honoring XDG paths in `services/rag_backend/adapters/storage/catalog.py` and `services/rag_backend/adapters/storage/audit_log.py`.",
      files := ["services/rag_backend/adapters/storage/catalog.py", "services/rag_backend/adapters/storage/audit_log.py"],
      parallel := false,
      dependencies := ["T019"]
    },
    { id := "T024",
      title := "Implement Phoenix/structlog instrumentation helpers",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Implement Phoenix/structlog instrumentation helpers in `services/rag_backend/adapters/observability/telemetry.py`.",
      files := ["services/rag_backend/adapters/observability/telemetry.py"],
      parallel := false,
      dependencies := ["T018", "T019", "T020", "T021"]
    },
    { id := "T025",
      title := "Implement resumable ingestion recovery for interrupted jobs",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Implement resumable ingestion recovery for interrupted jobs in `services/rag_backend/domain/job_recovery.py`.",
      files := ["services/rag_backend/domain/job_recovery.py"],
      parallel := false,
      dependencies := ["T020"]
    },
    { id := "T026",
      title := "Implement corrupt source quarantine workflow updates",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Implement corrupt source quarantine workflow updates in `services/rag_backend/domain/source_service.py`.",
      files := ["services/rag_backend/domain/source_service.py"],
      parallel := false,
      dependencies := ["T021", "T025"]
    },
    { id := "T027",
      title := "Record Milestone 3 completion",
      phase := Phase.foundational,
      stage := "Milestone 3 - Infrastructure adapters & resilience",
      description := "Record Milestone 3 completion in `specs/001-rag-cli/milestones.md` after adapter and resilience tests pass.",
      files := ["specs/001-rag-cli/milestones.md"],
      parallel := false,
      dependencies := ["T022", "T023", "T024", "T025", "T026"]
    },
    { id := "T028",
      title := "Add failing backend offline compliance tests that block outbound HTTP",
      phase := Phase.foundational,
      stage := "Milestone 3A - Offline guarantee",
      description := "Add failing backend offline compliance tests that block outbound HTTP in `tests/python/integration/test_offline_guards.py`.",
      files := ["tests/python/integration/test_offline_guards.py"],
      parallel := true,
      dependencies := ["T027"]
    },
    { id := "T029",
      title := "Add failing CLI offline compliance tests covering `ragman` and `ragadmin` flows",
      phase := Phase.foundational,
      stage := "Milestone 3A - Offline guarantee",
      description := "Add failing CLI offline compliance tests covering `ragman` and `ragadmin` flows in `tests/go/contract/offline_guard_test.go`.",
      files := ["ragman", "ragadmin", "tests/go/contract/offline_guard_test.go"],
      parallel := true,
      dependencies := ["T027"]
    },
    { id := "T030",
      title := "Implement backend offline enforcement and safe adapter guards",
      phase := Phase.foundational,
      stage := "Milestone 3A - Offline guarantee",
      description := "Implement backend offline enforcement and safe adapter guards in `services/rag_backend/application/offline_guard.py`.",
      files := ["services/rag_backend/application/offline_guard.py"],
      parallel := false,
      dependencies := ["T028"]
    },
    { id := "T031",
      title := "Implement shared Go IPC offline enforcement and structured logging",
      phase := Phase.foundational,
      stage := "Milestone 3A - Offline guarantee",
      description := "Implement shared Go IPC offline enforcement and structured logging in `cli/shared/ipc/client.go`.",
      files := ["cli/shared/ipc/client.go"],
      parallel := false,
      dependencies := ["T029", "T010", "T011"]
    },
    { id := "T032",
      title := "Record offline milestone completion",
      phase := Phase.foundational,
      stage := "Milestone 3A - Offline guarantee",
      description := "Record offline milestone completion in `specs/001-rag-cli/milestones.md` after offline test pass.",
      files := ["specs/001-rag-cli/milestones.md"],
      parallel := false,
      dependencies := ["T030", "T031"]
    },
    { id := "T033",
      title := "Add failing transport endpoint tests for `/v1/query`, `/v1/sources`, `/v1/index/reindex`, and `/v1/admin/*`",
      phase := Phase.foundational,
      stage := "Milestone 4 - Transport endpoints",
      description := "Add failing transport endpoint tests for `/v1/query`, `/v1/sources`, `/v1/index/reindex`, and `/v1/admin/*` in `tests/python/contract/test_transport_endpoints.py`.",
      files := ["/v1/query", "/v1/sources", "/v1/index/reindex", "/v1/admin/*", "tests/python/contract/test_transport_endpoints.py"],
      parallel := true,
      dependencies := ["T032"]
    },
    { id := "T034",
      title := "Add failing stale-index rejection tests for `/v1/query` returning 409",
      phase := Phase.foundational,
      stage := "Milestone 4 - Transport endpoints",
      description := "Add failing stale-index rejection tests for `/v1/query` returning 409 in `tests/python/contract/test_transport_stale_index.py`.",
      files := ["/v1/query", "tests/python/contract/test_transport_stale_index.py"],
      parallel := true,
      dependencies := ["T032"]
    },
    { id := "T035",
      title := "Map domain ports to socket handlers with standardized errors",
      phase := Phase.foundational,
      stage := "Milestone 4 - Transport endpoints",
      description := "Map domain ports to socket handlers with standardized errors in `services/rag_backend/adapters/transport/handlers.py`.",
      files := ["services/rag_backend/adapters/transport/handlers.py"],
      parallel := false,
      dependencies := ["T033", "T034", "T015", "T016"]
    },
    { id := "T036",
      title := "Implement `/v1/admin/init` verification and stale-index rejection logic",
      phase := Phase.foundational,
      stage := "Milestone 4 - Transport endpoints",
      description := "Implement `/v1/admin/init` verification and stale-index rejection logic in `services/rag_backend/adapters/transport/handlers.py`.",
      files := ["/v1/admin/init", "services/rag_backend/adapters/transport/handlers.py"],
      parallel := false,
      dependencies := ["T035"]
    },
    { id := "T037",
      title := "Record Milestone 4 completion",
      phase := Phase.foundational,
      stage := "Milestone 4 - Transport endpoints",
      description := "Record Milestone 4 completion in `specs/001-rag-cli/milestones.md` after endpoint tests pass.",
      files := ["specs/001-rag-cli/milestones.md"],
      parallel := false,
      dependencies := ["T033", "T034", "T035", "T036"]
    },
    { id := "T038",
      title := "Add failing Go unit tests for request builders and decoders",
      phase := Phase.foundational,
      stage := "Milestone 5 - Shared Go IPC client",
      description := "Add failing Go unit tests for request builders and decoders in `tests/go/unit/ipc/client_test.go`.",
      files := ["tests/go/unit/ipc/client_test.go"],
      parallel := true,
      dependencies := ["T037"]
    },
    { id := "T039",
      title := "Implement request builders, decoders, and retry/backoff logic",
      phase := Phase.foundational,
      stage := "Milestone 5 - Shared Go IPC client",
      description := "Implement request builders, decoders, and retry/backoff logic in `cli/shared/ipc/client.go`.",
      files := ["cli/shared/ipc/client.go"],
      parallel := false,
      dependencies := ["T038", "T031"]
    },
    { id := "T040",
      title := "Record Milestone 5 completion",
      phase := Phase.foundational,
      stage := "Milestone 5 - Shared Go IPC client",
      description := "Record Milestone 5 completion in `specs/001-rag-cli/milestones.md` once shared IPC tests turn green.",
      files := ["specs/001-rag-cli/milestones.md"],
      parallel := false,
      dependencies := ["T038", "T039"]
    }
  ]

def userStory1Tasks : List Task :=
  [
    { id := "T041",
      title := "Add failing `ragman` CLI contract tests for success and no-answer paths",
      phase := Phase.userStory1,
      stage := "User Story 1 - Tests (MANDATORY)",
      description := "Add failing `ragman` CLI contract tests for success and no-answer paths in `tests/go/contract/ragman_query_test.go`.",
      files := ["ragman", "tests/go/contract/ragman_query_test.go"],
      parallel := true,
      dependencies := ["T040"]
    },
    { id := "T042",
      title := "Add failing backend integration test asserting citation and confidence fields",
      phase := Phase.userStory1,
      stage := "User Story 1 - Tests (MANDATORY)",
      description := "Add failing backend integration test asserting citation and confidence fields in `tests/python/integration/test_query_flow.py`.",
      files := ["tests/python/integration/test_query_flow.py"],
      parallel := true,
      dependencies := ["T040"]
    },
    { id := "T043",
      title := "Add failing latency benchmark tests for SC-001",
      phase := Phase.userStory1,
      stage := "User Story 1 - Tests (MANDATORY)",
      description := "Add failing latency benchmark tests for SC-001 in `tests/python/performance/test_query_latency.py`.",
      files := ["tests/python/performance/test_query_latency.py"],
      parallel := true,
      dependencies := ["T040"]
    },
    { id := "T044",
      title := "Add failing context-limit truncation tests",
      phase := Phase.userStory1,
      stage := "User Story 1 - Tests (MANDATORY)",
      description := "Add failing context-limit truncation tests in `tests/python/integration/test_context_limits.py`.",
      files := ["tests/python/integration/test_context_limits.py"],
      parallel := true,
      dependencies := ["T040"]
    },
    { id := "T045",
      title := "Implement query application orchestrator with telemetry",
      phase := Phase.userStory1,
      stage := "User Story 1 - Implementation",
      description := "Implement query application orchestrator with telemetry in `services/rag_backend/application/query_runner.py`.",
      files := ["services/rag_backend/application/query_runner.py"],
      parallel := false,
      dependencies := ["T041", "T042"]
    },
    { id := "T046",
      title := "Instrument latency metrics and thresholds",
      phase := Phase.userStory1,
      stage := "User Story 1 - Implementation",
      description := "Instrument latency metrics and thresholds in `services/rag_backend/application/query_metrics.py`.",
      files := ["services/rag_backend/application/query_metrics.py"],
      parallel := false,
      dependencies := ["T042", "T043", "T024"]
    },
    { id := "T047",
      title := "Implement `ragman` root and query spf13/cobra commands",
      phase := Phase.userStory1,
      stage := "User Story 1 - Implementation",
      description := "Implement `ragman` root and query spf13/cobra commands in `cli/ragman/cmd/root.go` and `cli/ragman/cmd/query.go`.",
      files := ["ragman", "cli/ragman/cmd/root.go", "cli/ragman/cmd/query.go"],
      parallel := false,
      dependencies := ["T045", "T046", "T033", "T034", "T035", "T036", "T038", "T039"],
      notes := ["Transport dependency requires Milestone 4 and Milestone 5 readiness."]
    },
    { id := "T048",
      title := "Implement terminal/JSON renderers with citation, confidence, and truncation messaging",
      phase := Phase.userStory1,
      stage := "User Story 1 - Implementation",
      description := "Implement terminal/JSON renderers with citation, confidence, and truncation messaging in `cli/ragman/internal/io/renderer.go`.",
      files := ["cli/ragman/internal/io/renderer.go"],
      parallel := false,
      dependencies := ["T047"]
    },
    { id := "T049",
      title := "Record Milestone 7 completion",
      phase := Phase.userStory1,
      stage := "User Story 1 - Implementation",
      description := "Record Milestone 7 completion in `specs/001-rag-cli/milestones.md` after CLI and backend tests pass.",
      files := ["specs/001-rag-cli/milestones.md"],
      parallel := false,
      dependencies := ["T045", "T046", "T047", "T048"]
    }
  ]

def userStory2Tasks : List Task :=
  [
    { id := "T050",
      title := "Add failing `ragadmin` contract tests for listing and adding sources",
      phase := Phase.userStory2,
      stage := "User Story 2 - Tests (MANDATORY)",
      description := "Add failing `ragadmin` contract tests for listing and adding sources in `tests/go/contract/ragadmin_sources_list_add_test.go`.",
      files := ["ragadmin", "tests/go/contract/ragadmin_sources_list_add_test.go"],
      parallel := true,
      dependencies := ["T049"]
    },
    { id := "T051",
      title := "Add failing `ragadmin` contract tests for updating source metadata",
      phase := Phase.userStory2,
      stage := "User Story 2 - Tests (MANDATORY)",
      description := "Add failing `ragadmin` contract tests for updating source metadata in `tests/go/contract/ragadmin_sources_update_test.go`.",
      files := ["ragadmin", "tests/go/contract/ragadmin_sources_update_test.go"],
      parallel := true,
      dependencies := ["T049"]
    },
    { id := "T052",
      title := "Add failing `ragadmin` contract tests for removing sources and verifying quarantine",
      phase := Phase.userStory2,
      stage := "User Story 2 - Tests (MANDATORY)",
      description := "Add failing `ragadmin` contract tests for removing sources and verifying quarantine in `tests/go/contract/ragadmin_sources_remove_test.go`.",
      files := ["ragadmin", "tests/go/contract/ragadmin_sources_remove_test.go"],
      parallel := true,
      dependencies := ["T049"]
    },
    { id := "T053",
      title := "Add failing backend integration tests for catalog lifecycle and alias collision handling",
      phase := Phase.userStory2,
      stage := "User Story 2 - Tests (MANDATORY)",
      description := "Add failing backend integration tests for catalog lifecycle and alias collision handling in `tests/python/integration/test_source_catalog.py`.",
      files := ["tests/python/integration/test_source_catalog.py"],
      parallel := true,
      dependencies := ["T049"]
    },
    { id := "T054",
      title := "Add failing reindex performance tests for SC-002",
      phase := Phase.userStory2,
      stage := "User Story 2 - Tests (MANDATORY)",
      description := "Add failing reindex performance tests for SC-002 in `tests/python/performance/test_reindex_duration.py`.",
      files := ["tests/python/performance/test_reindex_duration.py"],
      parallel := true,
      dependencies := ["T049"]
    },
    { id := "T055",
      title := "Implement source catalog service for list/add flows with validation",
      phase := Phase.userStory2,
      stage := "User Story 2 - Implementation",
      description := "Implement source catalog service for list/add flows with validation in `services/rag_backend/application/source_catalog.py`.",
      files := ["services/rag_backend/application/source_catalog.py"],
      parallel := false,
      dependencies := ["T050", "T053"]
    },
    { id := "T056",
      title := "Implement source update workflows enforcing metadata validation",
      phase := Phase.userStory2,
      stage := "User Story 2 - Implementation",
      description := "Implement source update workflows enforcing metadata validation in `services/rag_backend/application/source_catalog.py`.",
      files := ["services/rag_backend/application/source_catalog.py"],
      parallel := false,
      dependencies := ["T055", "T051"]
    },
    { id := "T057",
      title := "Implement source removal and quarantine flows",
      phase := Phase.userStory2,
      stage := "User Story 2 - Implementation",
      description := "Implement source removal and quarantine flows in `services/rag_backend/application/source_catalog.py`.",
      files := ["services/rag_backend/application/source_catalog.py"],
      parallel := false,
      dependencies := ["T055", "T052"]
    },
    { id := "T058",
      title := "Implement `ragadmin` sources spf13/cobra commands with table/JSON output",
      phase := Phase.userStory2,
      stage := "User Story 2 - Implementation",
      description := "Implement `ragadmin` sources spf13/cobra commands with table/JSON output in `cli/ragadmin/cmd/sources.go`.",
      files := ["ragadmin", "cli/ragadmin/cmd/sources.go"],
      parallel := false,
      dependencies := ["T055", "T056", "T057", "T033", "T034", "T035", "T036", "T038", "T039"],
      notes := ["Transport dependency requires Milestone 4 and Milestone 5 readiness."]
    },
    { id := "T059",
      title := "Implement `ragadmin reindex` spf13/cobra command with progress feedback and timing output",
      phase := Phase.userStory2,
      stage := "User Story 2 - Implementation",
      description := "Implement `ragadmin reindex` spf13/cobra command with progress feedback and timing output in `cli/ragadmin/cmd/reindex.go`.",
      files := ["ragadmin reindex", "cli/ragadmin/cmd/reindex.go"],
      parallel := false,
      dependencies := ["T055", "T054", "T058"]
    },
    { id := "T060",
      title := "Wire audit logging and language validation for mutations",
      phase := Phase.userStory2,
      stage := "User Story 2 - Implementation",
      description := "Wire audit logging and language validation for mutations in `services/rag_backend/adapters/storage/audit_log.py`.",
      files := ["services/rag_backend/adapters/storage/audit_log.py"],
      parallel := false,
      dependencies := ["T055", "T056", "T057", "T024"]
    },
    { id := "T061",
      title := "Record Milestone 6 completion",
      phase := Phase.userStory2,
      stage := "User Story 2 - Implementation",
      description := "Record Milestone 6 completion in `specs/001-rag-cli/milestones.md` after CRUD tests pass.",
      files := ["specs/001-rag-cli/milestones.md"],
      parallel := false,
      dependencies := ["T055", "T056", "T057", "T058", "T059", "T060"]
    }
  ]

def userStory3Tasks : List Task :=
  [
    { id := "T062",
      title := "Add failing integration tests for init bootstrapping and health diagnostics",
      phase := Phase.userStory3,
      stage := "User Story 3 - Tests (MANDATORY)",
      description := "Add failing integration tests for init bootstrapping and health diagnostics in `tests/python/integration/test_init_health.py`.",
      files := ["tests/python/integration/test_init_health.py"],
      parallel := true,
      dependencies := ["T061"]
    },
    { id := "T063",
      title := "Add failing `ragadmin` contract tests for init and health output",
      phase := Phase.userStory3,
      stage := "User Story 3 - Tests (MANDATORY)",
      description := "Add failing `ragadmin` contract tests for init and health output in `tests/go/contract/ragadmin_health_test.go`.",
      files := ["ragadmin", "tests/go/contract/ragadmin_health_test.go"],
      parallel := true,
      dependencies := ["T061"]
    },
    { id := "T064",
      title := "Add failing disk capacity threshold tests",
      phase := Phase.userStory3,
      stage := "User Story 3 - Tests (MANDATORY)",
      description := "Add failing disk capacity threshold tests in `tests/python/integration/test_disk_capacity.py`.",
      files := ["tests/python/integration/test_disk_capacity.py"],
      parallel := true,
      dependencies := ["T061"]
    },
    { id := "T065",
      title := "Add failing missing or corrupt source detection tests",
      phase := Phase.userStory3,
      stage := "User Story 3 - Tests (MANDATORY)",
      description := "Add failing missing or corrupt source detection tests in `tests/python/integration/test_source_health_failures.py`.",
      files := ["tests/python/integration/test_source_health_failures.py"],
      parallel := true,
      dependencies := ["T061"]
    },
    { id := "T066",
      title := "Implement init orchestration verifying Ollama/Weaviate readiness and seeding sources",
      phase := Phase.userStory3,
      stage := "User Story 3 - Implementation",
      description := "Implement init orchestration verifying Ollama/Weaviate readiness and seeding sources in `services/rag_backend/application/init_service.py`.",
      files := ["services/rag_backend/application/init_service.py"],
      parallel := false,
      dependencies := ["T062", "T063"]
    },
    { id := "T067",
      title := "Implement health evaluation aggregator producing remediation guidance and disk checks",
      phase := Phase.userStory3,
      stage := "User Story 3 - Implementation",
      description := "Implement health evaluation aggregator producing remediation guidance and disk checks in `services/rag_backend/application/health_service.py`.",
      files := ["services/rag_backend/application/health_service.py"],
      parallel := false,
      dependencies := ["T064", "T065", "T055", "T056", "T057"],
      notes := ["Catalog dependency requires source catalog completeness."]
    },
    { id := "T068",
      title := "Implement `ragadmin init` and `ragadmin health` spf13/cobra commands with structured logging",
      phase := Phase.userStory3,
      stage := "User Story 3 - Implementation",
      description := "Implement `ragadmin init` and `ragadmin health` spf13/cobra commands with structured logging in `cli/ragadmin/cmd/init.go` and `cli/ragadmin/cmd/health.go`.",
      files := ["ragadmin init", "ragadmin health", "cli/ragadmin/cmd/init.go", "cli/ragadmin/cmd/health.go"],
      parallel := false,
      dependencies := ["T066", "T067", "T033", "T034", "T035", "T036", "T038", "T039"],
      notes := ["Transport dependency requires Milestone 4 and Milestone 5 readiness."]
    },
    { id := "T069",
      title := "Persist init and health audit entries with trace IDs",
      phase := Phase.userStory3,
      stage := "User Story 3 - Implementation",
      description := "Persist init and health audit entries with trace IDs in `services/rag_backend/adapters/storage/audit_log.py`.",
      files := ["services/rag_backend/adapters/storage/audit_log.py"],
      parallel := false,
      dependencies := ["T066", "T067", "T068", "T060"]
    }
  ]

def polishTasks : List Task :=
  [
    { id := "T070",
      title := "Add end-to-end CLIbackend contract suite covering FR-001-FR-011",
      phase := Phase.polish,
      stage := "Polish and cross cutting",
      description := "Add end-to-end CLIbackend contract suite covering FR-001-FR-011 in `tests/python/contract/test_end_to_end.py`.",
      files := ["tests/python/contract/test_end_to_end.py"],
      parallel := true,
      dependencies := ["T069", "T024", "T028", "T029"]
    },
    { id := "T071",
      title := "Add observability assertions for Phoenix traces and structured logs",
      phase := Phase.polish,
      stage := "Polish and cross cutting",
      description := "Add observability assertions for Phoenix traces and structured logs in `tests/python/integration/test_observability.py`.",
      files := ["tests/python/integration/test_observability.py"],
      parallel := true,
      dependencies := ["T069", "T024"]
    },
    { id := "T072",
      title := "Record Milestone 8 completion",
      phase := Phase.polish,
      stage := "Polish and cross cutting",
      description := "Record Milestone 8 completion in `specs/001-rag-cli/milestones.md` after end-to-end suites pass.",
      files := ["specs/001-rag-cli/milestones.md"],
      parallel := false,
      dependencies := ["T070", "T071"]
    },
    { id := "T073",
      title := "Run offline validation suite with network-disabled runs",
      phase := Phase.polish,
      stage := "Polish and cross cutting",
      description := "Run offline validation suite with network-disabled runs in `tests/system/test_offline_validation.sh`.",
      files := ["tests/system/test_offline_validation.sh"],
      parallel := false,
      dependencies := ["T028", "T029", "T030", "T031", "T032", "T070"]
    },
    { id := "T074",
      title := "Run performance validation suite confirming SC-001 and SC-002",
      phase := Phase.polish,
      stage := "Polish and cross cutting",
      description := "Run performance validation suite confirming SC-001 and SC-002 in `tests/system/test_performance_validation.py`.",
      files := ["tests/system/test_performance_validation.py"],
      parallel := false,
      dependencies := ["T043", "T054", "T070"]
    },
    { id := "T075",
      title := "Update ragman CLI usage guide with new workflows",
      phase := Phase.polish,
      stage := "Polish and cross cutting",
      description := "Update ragman CLI usage guide with new workflows in `docs/guides/cli/ragman.md`.",
      files := ["docs/guides/cli/ragman.md"],
      parallel := false,
      dependencies := ["T048", "T070"]
    },
    { id := "T076",
      title := "Update ragadmin CLI usage guide with new workflows",
      phase := Phase.polish,
      stage := "Polish and cross cutting",
      description := "Update ragadmin CLI usage guide with new workflows in `docs/guides/cli/ragadmin.md`.",
      files := ["docs/guides/cli/ragadmin.md"],
      parallel := false,
      dependencies := ["T058", "T068", "T070"]
    },
    { id := "T077",
      title := "Update Unix socket ADR with finalized port mappings",
      phase := Phase.polish,
      stage := "Polish and cross cutting",
      description := "Update Unix socket ADR with finalized port mappings in `docs/adr/0001-unix-socket-ipc.md`.",
      files := ["docs/adr/0001-unix-socket-ipc.md"],
      parallel := false,
      dependencies := ["T035", "T036", "T070"]
    },
    { id := "T078",
      title := "Document Quickstart validation results and troubleshooting notes",
      phase := Phase.polish,
      stage := "Polish and cross cutting",
      description := "Document Quickstart validation results and troubleshooting notes in `specs/001-rag-cli/quickstart.md`.",
      files := ["specs/001-rag-cli/quickstart.md"],
      parallel := false,
      dependencies := ["T073", "T074", "T070", "T071"]
    }
  ]

def allTasks : List Task :=
  setupTasks ++ foundationalTasks ++ userStory1Tasks ++ userStory2Tasks ++ userStory3Tasks ++ polishTasks

def tasksByPhase (phase : Phase) : List Task :=
  match phase with
  | Phase.setup => setupTasks
  | Phase.foundational => foundationalTasks
  | Phase.userStory1 => userStory1Tasks
  | Phase.userStory2 => userStory2Tasks
  | Phase.userStory3 => userStory3Tasks
  | Phase.polish => polishTasks

def tasksByStage (stage : String) : List Task :=
  allTasks.filter fun t => t.stage = stage

def stageNames : List String :=
  allTasks.foldl (fun acc t => if acc.contains t.stage then acc else acc ++ [t.stage]) []

def pendingTasks : List Task :=
  allTasks.filter fun t => t.status = TaskStatus.todo

def completedTasks : List Task :=
  allTasks.filter fun t => t.status = TaskStatus.done

def blockedTasks : List Task :=
  allTasks.filter fun t => t.status = TaskStatus.blocked

def uniqueTaskIds : Prop :=
  (allTasks.map (·.id)).Nodup

def milestoneDependencies : List (String × List String) :=
  [
    ("ragman transport readiness", ["T033", "T034", "T035", "T036", "T038", "T039"]),
    ("ragman command enablement", ["T047", "T048"]),
    ("ragadmin transport readiness", ["T033", "T034", "T035", "T036", "T038", "T039"]),
    ("ragadmin catalog readiness", ["T055", "T056", "T057"]),
    ("offline validation readiness", ["T024", "T028", "T029", "T030", "T031", "T032", "T070", "T071", "T072", "T073", "T074"])
  ]

end Specs001RagCli
