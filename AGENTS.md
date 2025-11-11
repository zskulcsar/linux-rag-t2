## Superpowers System

<EXTREMELY_IMPORTANT>
You have superpowers. Superpowers teach you new skills and capabilities.
**MANDATORY** read the `using-superpowers` instructions at `{CODEX_HOME}/skills/using-superpowers/SKILL.md`.

**Skills naming:**
- Superpowers skills: `superpowers:skill-name` (from {CODEX_HOME}/skills/)
- Personal skills: `skill-name` (from ~/.codex/skills/)
- Personal skills override superpowers skills when names match

**Critical Rules:**
- Before ANY task, review the skills list (shown below)
- If a relevant skill exists, you must load it from the `{CODEX_HOME}/skills` folder
- Announce: "I've read the [Skill Name] skill and I'm using it to [purpose]"
- NEVER skip mandatory workflows (brainstorming before coding, TDD, systematic debugging)

**Skills location:**
- Superpowers skills: `{CODEX_HOME}/skills/`
- Personal skills: ~/.codex/skills/ (override superpowers when names match)

IF A SKILL APPLIES TO YOUR TASK, YOU DO NOT HAVE A CHOICE. YOU MUST USE IT.
</EXTREMELY_IMPORTANT>

# linux-rag-t2 Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-31

## Active Technologies

- Go 1.23 for CLIs, Python 3.12 backend managed via uv + Go `spf13/cobra`, Go stdlib `net/unix`, Python `weaviate-client`, `arize-phoenix`, `structlog`, `pytest-asyncio`, local Ollama HTTP API (001-rag-cli)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Go 1.23 for CLIs, Python 3.12 backend managed via uv: Follow standard conventions

## Recent Changes

- 001-rag-cli: Added Go 1.23 for CLIs, Python 3.12 backend managed via uv + Go `spf13/cobra`, Go stdlib `net/unix`, Python `weaviate-client`, `arize-phoenix`, `structlog`, `pytest-asyncio`, local Ollama HTTP API

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
