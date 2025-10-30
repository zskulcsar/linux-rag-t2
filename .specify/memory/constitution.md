<!--
Sync Impact Report
Version change: N/A -> 0.0.1
Modified principles: None (initial ratification)
Added sections: Core Principles; Automation & Tooling Requirements; Development Workflow & Quality Gates; Governance
Removed sections: None
Templates requiring updates:
- updated .specify/templates/plan-template.md (constitution gates aligned)
- updated .specify/templates/tasks-template.md (tests mandate enforced)
Follow-up TODOs: None
-->
# Linux RAG T2 Constitution

## Core Principles

### I. Standards & Typing Discipline (NON-NEGOTIABLE)
- All Python code MUST comply with PEP-8 and PEP-257; Ruff is the single formatter, linter, and import sorter.
- Public modules, classes, functions, and CLI entry points MUST provide complete type hints; mypy runs in strict mode on every PR.
- Imports MUST stay safe: avoid network I/O and raise precise domain exceptions that map to safe client responses.
Rationale: Uniform style and strict typing produce predictable, debuggable modules with minimal runtime surprises.

### II. Documentation as Contract
- Apply Google-style docstrings consistently; every public surface documents purpose, arguments, returns, and examples where useful.
- Each module maintains docs under `docs/`; services publish OpenAPI references there so the MkDocs site remains authoritative.
- Significant architectural or process changes MUST include an ADR under `docs/adr/` before implementation closes.
Rationale: Documentation-first delivery keeps knowledge discoverable and guards against implicit tribal memory.

### III. Test-First Quality Gates
- Every change MUST land with pytest coverage; new public APIs include contract tests derived from their OpenAPI definitions.
- Libraries maintain >=90% coverage and services >=80%; coverage gates fail the build if violated.
- Tests remain hermetic: mock external I/O, seed RNGs, and include performance smoke checks for hot paths.
Rationale: Enforced testing discipline prevents regressions and validates behaviour before code reaches users.

### IV. Modular Monorepo Delivery
- The repository layout MUST follow the monorepo structure so each app, service, and package is independently buildable, testable, versioned, and container-deployable.
- Use uv for environment management and locking; track hashes in VCS and support the latest two CPython minor versions in CI.
- Automation guardrails (Ruff, mypy, pytest with coverage, pip-audit, Trivy for services, secret scanning, docs and OpenAPI builds) MUST run on every PR; `main` also emits SBOMs, release artifacts, provenance attestations, and deploys docs.
- Modules follow SemVer; breaking changes require a major bump plus migration notes and changelog updates.
Rationale: Modular delivery with automated guardrails ensures repeatable builds and trustworthy releases.

### V. Observability & Security Readiness
- Services MUST expose health and readiness probes plus structured JSON logs carrying request IDs and W3C trace IDs without PII.
- Metrics MUST record latency, error rate, throughput, and resource usage; tracing propagates context across upstream and downstream calls.
- Auth is required by default with least-privilege scopes and strict server-side validation; local testing relaxations follow the dependency policy constraints.
Rationale: Strong observability and security guarantees keep the platform operable, diagnosable, and safe to promote.

## Automation & Tooling Requirements

- Pre-commit enforces Ruff, mypy, and detect-secrets hooks before any commit lands.
- uv lockfiles, dependency hashes, and environment definitions MUST stay current and validated across the supported Python versions.
- GitHub Actions pipelines implement the guardrails defined in the Core Principles, including vulnerability scanning and documentation builds.
- Container images and Python artifacts MUST be signed and stored with provenance before promotion beyond staging.

## Development Workflow & Quality Gates

- Feature work begins with `/speckit.spec`, `/speckit.plan`, and `/speckit.tasks`; these documents MUST enumerate documentation, testing, observability, and release impacts explicitly.
- Code reviews verify adherence to this constitution, enforce coverage and lint gates, and ensure documentation, including OpenAPI exports, is updated alongside code.
- Constitution checks occur at plan approval and before merge; violations require documented justification in the Complexity Tracking table and CODEOWNERS sign-off.
- Release candidates MUST satisfy observability readiness probes and have validated health checks before staging or production promotion.

## Governance

This constitution supersedes prior guidance for the Linux RAG T2 repository. Amendments require a pull request that:

1. Proposes the wording change with accompanying rationale and migration guidance if behaviour shifts.
2. Updates all dependent templates and documentation impacted by the change.
3. Receives approval from the CODEOWNERS set and passes all automation guardrails.

Version numbers follow SemVer semantics: MAJOR for breaking governance changes, MINOR for new or materially expanded principles or sections, and PATCH for clarifications. Compliance reviews take place at least quarterly and during every release retrospective; gaps trigger follow-up tasks tracked to closure. Non-compliant changes MUST be remediated before promotion beyond staging unless an explicit, time-bound waiver is documented and approved by CODEOWNERS.

**Version**: 0.0.1 | **Ratified**: 2025-10-30 | **Last Amended**: 2025-10-30
