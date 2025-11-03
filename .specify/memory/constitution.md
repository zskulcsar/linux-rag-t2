<!--
Sync Impact Report
Version change: 0.4.0 -> 0.5.0
Modified principles: V. Observability & Security Readiness -> V. Observability & Diagnostics Logging; Development Workflow & Quality Gates -> Development Workflow & Quality Gates
Added sections: None
Removed sections: None
Templates requiring updates:
- updated .specify/templates/plan-template.md (constitution gates cover hex architecture, maintainability, simplicity, and logging standards)
- updated .specify/templates/tasks-template.md (tasks highlight hex architecture, maintainability, simplicity, and logging guardrails)
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
- Apply Google-style docstrings consistently; every public surface documents purpose, arguments, returns, and examples are useful.
- Each module maintains docs under `docs/`; services publish OpenAPI references there so the MkDocs site remains authoritative.
- Significant architectural or process changes MUST include an ADR under `docs/adr/` before implementation closes.
Rationale: Documentation-first delivery keeps knowledge discoverable and guards against implicit tribal memory.

### III. Test-First Quality Gates
- Every change MUST land with pytest coverage; new public APIs include contract tests derived from their OpenAPI definitions.
- Libraries maintain >=90% coverage and services >=80%; coverage gates fail the build if violated.
- Tests remain hermetic: mock external I/O, seed RNGs, and include performance smoke checks for hot paths.
Rationale: Enforced testing discipline prevents regressions and validates behaviour before code reaches users.

### IV. Modular Monorepo & Hexagonal Architecture
- The repository layout MUST follow the monorepo structure so each app, service, and package is independently buildable, testable, versioned, and container-deployable.
- All services and CLIs MUST follow hexagonal architecture: domain logic stays in framework-agnostic core modules; entry points interact through well-defined ports; adapters isolate infrastructure concerns (storage, vector databases, LLM backends, CLI IO).
- New features MUST document and implement port interfaces before wiring adapters; cross-module calls interact via ports rather than direct adapter access.
- Use uv for environment management and locking; track hashes in VCS and support the latest two CPython minor versions in CI.
- Automation guardrails (Ruff, mypy, pytest with coverage, pip-audit, Trivy for services, secret scanning, docs and OpenAPI builds) MUST run on every PR; `main` also emits SBOMs, release artifacts, provenance attestations, and deploys docs.
- Modules follow SemVer; breaking changes require a major bump plus migration notes and changelog updates.
Rationale: Modular delivery with automated guardrails ensures repeatable builds and trustworthy releases while hexagonal boundaries keep domain logic isolated and testable.

### V. Observability & Diagnostics Logging
- Services MUST expose health and readiness probes plus structured JSON logs carrying request IDs and W3C trace IDs without leaking sensitive data.
- Metrics MUST record latency, error rate, throughput, and resource usage; tracing propagates context across upstream and downstream calls for local troubleshooting.
- Public-facing APIs MUST be instrumented with the approved call-tracing decorator so entry/exit events emit structured JSON logs (correlation IDs, sanitised parameters, and outcomes) without manual boilerplate.
- Critical multi-step workflows (e.g., ingestion batches, quarantine updates, query orchestration) MUST run inside the approved observability context manager so start/finish, duration, and significant checkpoints are recorded at INFO/DEBUG levels with structured metadata.
- The platform MUST provide an opt-in deep-tracing facility (e.g., `sys.settrace`/profiler hooks) that captures detailed execution when explicitly enabled; it remains disabled by default, filters sensitive data, and documents activation/deactivation workflow.
- Structured logs produced by decorators and context managers MUST remain JSON-friendly and include correlation/trace identifiers; additional manual logs MAY supplement these layers when domain-specific breadcrumbs are required.
- Baseline observability mechanisms MUST remain lightweight during normal operation; optional profiling/tracing modes MAY incur overhead but MUST be clearly documented and isolated behind explicit toggles.
- Automated tests MUST cover the decorator, context-manager, and tracing facilities to guarantee observability remains available and correctly wired.
Rationale: Rich observability and consistent diagnostics keep the locally hosted system debuggable without imposing unnecessary multi-user security controls.

### VI. Maintainable Code Structure
- Keep source files small enough to remain easy to understand; split responsibilities rather than ballooning single modules.
- Define each class in its own file unless a helper value object is tightly coupled and deliberately scoped.
- Preserve the hexagonal separation of domain services, ports, and adapters by refactoring once files exceed agreed complexity thresholds.
Rationale: Focused files improve reviewability, reduce merge conflicts, and keep architectural boundaries enforceable over time.

### VII. Simplicity First (KISS)
- Design features with the simplest viable architecture; avoid speculative abstractions, premature generalisation, or unnecessary layers.
- Prefer straightforward adapters and domain services; justify any added indirection, configuration, or polymorphism within the plan before implementation.
- Break complex flows into incremental steps that can be independently delivered and observed; remove dead code and unused integrations promptly.
Rationale: Keeping implementations simple reduces onboarding friction, lowers maintenance cost, and keeps failure modes obvious.

## Automation & Tooling Requirements

- Pre-commit enforces Ruff, mypy, and detect-secrets hooks before any commit lands.
- uv lockfiles, dependency hashes, and environment definitions MUST stay current and validated across the supported Python versions.
- GitHub Actions pipelines implement the guardrails defined in the Core Principles, including vulnerability scanning and documentation builds.
- Container images and Python artifacts MUST be signed and stored with provenance before promotion beyond staging.

## Development Workflow & Quality Gates

- Feature work begins with `/speckit.spec`, `/speckit.plan`, and `/speckit.tasks`; these documents MUST enumerate documentation, testing, observability, and release impacts explicitly.
- Plans MUST include an architecture slice showing affected ports, adapters, and domain services to keep hexagonal boundaries explicit before implementation.
- Plans and code reviews MUST highlight any large-file refactors required to maintain small, focused modules and track follow-up tasks when files approach complexity limits.
- Plans MUST call out simplifications taken compared to alternative designs to enforce the KISS principle and avoid over-engineering.
- Plans MUST describe how the feature leverages the approved observability layers (decorators for baseline entry/exit traces, context managers for critical sections, tracing hooks for deep diagnostics) and identify any supplemental manual logs.
- Code reviews verify adherence to this constitution, enforce coverage and lint gates, and ensure documentation, including OpenAPI exports, is updated alongside code.
- Constitution checks occur at plan approval and before merge; violations require documented justification in the Complexity Tracking table and CODEOWNERS sign-off.
- Release candidates MUST satisfy observability readiness probes and have validated health checks before staging or production promotion.

## Governance

This constitution supersedes prior guidance for the Linux RAG T2 repository. Amendments require a pull request that:

1. Proposes the wording change with accompanying rationale and migration guidance if behaviour shifts.
2. Updates all dependent templates and documentation impacted by the change.
3. Receives approval from the CODEOWNERS set and passes all automation guardrails.

Version numbers follow SemVer semantics: MAJOR for breaking governance changes, MINOR for new or materially expanded principles or sections, and PATCH for clarifications. Compliance reviews take place at least quarterly and during every release retrospective; gaps trigger follow-up tasks tracked to closure. Non-compliant changes MUST be remediated before promotion beyond staging unless an explicit, time-bound waiver is documented and approved by CODEOWNERS.

**Version**: 0.5.0 | **Ratified**: 2025-10-30 | **Last Amended**: 2025-10-30
