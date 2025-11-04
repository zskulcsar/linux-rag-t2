---
name: python-logging
description: Use when writing or modifying Python code to ensure observability obligations are met with trace decorators, async trace contexts, and structured logging.
---

# Python Logging & Tracing

## Overview
Codex must wire observability exactly as mandated by Constitution §V and the backend design docs. Every public-facing function requires a trace decorator, critical sections must use the async context manager, and deeper diagnostics rely on the tracing controller. This skill captures the contract already enforced across `services/rag_backend`.

## When to Use
- Authoring new Python modules, functions, methods, or scripts
- Modifying existing Python logic that impacts control flow or external effects
- Implementing transport, domain, storage, or adapter code in this repo
- Reviewing code for observability compliance

Do NOT use only when editing documentation or pure data files with no Python code.

## Required Observability Stack
1. **Decorator entry logging (baseline)** – Every public function/method uses `@trace_call` (from `services.rag_backend.telemetry`) to record entry/exit with structured metadata.
2. **Telemetry context manager (critical sections)** – Wrap multi-step workflows inside `async_trace_section("component.operation", metadata={...})` or `trace_section(...)` for sync code.
3. **Tracing controller (deep diagnostics)** – Ensure handlers expose correlation IDs and pass through `trace_id` fields so tracing can be enabled without code changes.

These layers stack; do not omit earlier layers when adding deeper tracing.

## Canonical Examples
Use existing code as authoritative reference:
- `services/rag_backend/adapters/transport/server.py` – Shows `@trace_call` on helper functions AND `async_trace_section` around connection handling.
- `services/rag_backend/adapters/storage/catalog.py` – Demonstrates synchronous `trace_section` for file writes.
- `services/rag_backend/domain/source_service.py` – Domain service methods already decorated with `@trace_call`.

Quote these when in doubt; new code must mirror their structure.

## Implementation Checklist
- [ ] Add `from services.rag_backend.telemetry import trace_call, trace_section, async_trace_section` as needed.
- [ ] Decorate every public callable (`@trace_call` for sync/async functions).
- [ ] Supply meaningful metadata dictionaries (socket paths, correlation IDs, aliases, etc.) when entering trace sections.
- [ ] For async flows, wrap connection/IO loops with `async_trace_section("component.action", metadata=...)`.
- [ ] Emit structured log fields (`slog.String`, `slog.Int`, etc.) when using Go logging analogues.
- [ ] Propagate correlation IDs through responses and error payloads so tracing remains linked end-to-end.

## Common Mistakes
- Skipping `@trace_call` because "the context manager already logs" → violates baseline entry logging.
- Logging raw strings without metadata → loses structured context; always pass key/value pairs.
- Forgetting to close trace sections on errors → always wrap in `try/finally`.
- Adding new code under the transport layer without emitting correlation IDs.

## Quick Reference
- Decorate function: `@trace_call`.
- Async critical region: `async with async_trace_section("component.action", metadata={...}):`.
- Sync critical region: `with trace_section("component.action", metadata={...}):`.
- Error logging: emit structured metadata plus the exception string.

## Red Flags
- New Python file without telemetry imports.
- Added network/disk/database operations outside a trace section.
- Complex workflows lacking correlation IDs or metadata fields.

## Final Rule
If you change Python code, verify observability. No exceptions.
