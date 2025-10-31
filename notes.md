# Live notes

## /constitution

## /specify

## /clarify

## /plan

The initial prompt:
> Plan the project, as follows:
>  - The command line interfaces are standalone go binaries using spf13/Cobra framework.
>  - The command line communicates with the python backend for both ragman and ragadmin; This communication is hapenning over Unix sockets.
>  - The backend is using local ollama service for interfacing the LLM over HTTP.
>  - The backend is using weaviate as the knowledge source for ingestion, storage and retrieval using the `weaviate-client` python library.
>  - Tha backend should use `arize-phoenix` python library for observability.
>  - Although Ollama and Weaviate are dependencies, these are not managed by ragadmin other than **FR-005** to verify setup.

Output:
> • Planning Update
>
>  - Documented the end-to-end implementation approach, constitutional guardrails, and target structure for the Go CLIs and Python backend in specs/001-rag-cli/plan.md:1.
>  - Captured Phase 0 research decisions—including Cobra usage, ipc framing, Weaviate batching, Phoenix instrumentation, and test tooling—inside specs/001-rag-cli/research.md:3.
>  - Defined domain entities, validation, and state flows for sources, ingestion jobs, index versions, health checks, and audit logging in specs/001-rag-cli/data-model.md:3.
>  - Published the Unix-socket JSON API contract that the CLIs will consume via OpenAPI 3.1 at specs/001-rag-cli/contracts/backend-openapi.yaml:1.
>  - Added a developer quickstart covering prerequisites, backend launch, admin workflows, and validation commands in specs/001-rag-cli/quickstart.md:3, and refreshed the Codex agent context via AGENTS.md:1.
>
>  Artifacts:
>
>  - Branch: 001-rag-cli
>  - Implementation plan: specs/001-rag-cli/plan.md
>  - Phase 0/1 outputs: research.md, data-model.md, contracts/backend-openapi.yaml, quickstart.md, updated AGENTS.md
>
>  Next Steps:
>
>  1. Review and sign off on the plan/design package, then raise any clarifications before Phase 2 task breakdown.
>  2. Align stakeholders on the data model and IPC contract so implementation can begin against the documented schemas.
