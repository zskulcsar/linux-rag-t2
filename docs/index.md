# Linux RAG T2

This documentation portal aggregates design and implementation notes for the
local Linux Retrieval-Augmented Generation (RAG) toolchain. The project
combines Go-based command-line interfaces (`ragman`, `ragadmin`) with a Python
backend service orchestrating Weaviate, Ollama, and Phoenix integrations.

## Project Structure

- `cli/` – Go CLIs implemented with Cobra adhering to hexagonal architecture.
- `backend/src/` – Python service exposing the Unix-socket transport
  and domain orchestration.
- `tests/` – Contract, integration, and unit test suites across Go and Python.
- `specs/001-rag-cli/` – Approved specification, plan, tasks, and research
  artifacts guiding feature delivery.

Refer to the CLI guides for day-to-day usage, and consult the specification
under `specs/001-rag-cli/spec.md` for detailed functional requirements.
