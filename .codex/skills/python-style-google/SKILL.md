---
name: python-style-guide
description: "Apply the Linux RAG T2 Python style rules: PEP 8/257 formatting, Ruff enforcement, strict typing, and docstrings. Use when writing, reviewing, or refactoring Python code in this repo."
---

# Python Style Guide (Linux RAG T2)

This skill encodes the constitution-mandated Python standards for this repository. Apply it for every Python change.

## Core Principles

1. **Formatting & Linting**
   - Ruff is the single source of truth for formatting, linting, and import sorting. Run `ruff format` / `ruff check` (or the configured pre-commit hooks) until clean.
   - Respect Ruff configuration in `pyproject.toml`; do not hand-tweak formatting or disable rules without approval.

2. **Typing & Imports**
   - Public modules, classes, and functions require complete type hints. Use modern syntax (`list[str]`, `LogRecord | None`).
   - `from __future__ import annotations` is permitted only when necessary for forward references that Ruff/mypy accept; prefer explicit ordering and postponed evaluation via string annotations otherwise.
   - Group imports: standard library, third-party, local. Ruff’s sorter should enforce this order.

3. **Docstrings & Documentation**
   - Follow PEP 257 with Google-style docstrings (per constitution Section II). Every public symbol documents purpose, args, returns, raises, and examples when valuable.
   - Keep module-level docstrings for entry points and complex utilities.

4. **Error Handling**
   - Use precise exceptions; avoid bare `except Exception` unless re-raising with context.
   - Raise domain-specific errors that map to safe CLI responses. Never leak sensitive data in error messages or logs.

5. **Logging & Observability**
   - Leverage `structlog` (or configured logging facade) with the mandated `ClassName.method(params) :: message` pattern.
   - Include correlation/trace IDs when available and respect redaction guidelines.

6. **File & Directory Layout**
   - Use `pathlib.Path` and honour XDG base directories (`$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, `$XDG_RUNTIME_DIR`).
   - Always specify `encoding="utf-8"` when opening text files.

7. **Testing Expectations**
   - Tests accompany every change (see TDD skill). Python tests run under `pytest` with `pytest-asyncio` where required; keep them hermetic.

## Quick Checklist

- [ ] Ruff format + lint clean
- [ ] Type hints on all public surfaces
- [ ] Docstrings follow Google style
- [ ] Exceptions precise; no blanket catches
- [ ] Logging uses structured format with IDs
- [ ] Paths handled via `pathlib` and XDG
- [ ] Tests updated/added and pass locally

## References

- [PEP 8](https://peps.python.org/pep-0008/)
- [PEP 257](https://peps.python.org/pep-0257/)
- Ruff documentation: https://docs.astral.sh/ruff/
- Project constitution: `.specify/memory/constitution.md`
