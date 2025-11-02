---
description: Generate lean4 code for the implementation plan by processing and plannings all tasks defined in tasks.md
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).
You **MUST** use the configured MCP servers. use context7.
You **MUST** respect the ground rules established at `.specify/memory/constitution.md`.

## Goal

To provide a lean4 definition of the feature specified in the FEATURE_DIR based on the `spec.md`, `plan.md`, `tasks.md`, `research.md` and `data-model.md` files, so that the definition can be validated and can guide the implementation using `/speckit.implement` in a later step.

## Operating Constraints

**STRICTLY Lean4 code generation**: Do **not** generate any other code other than `lean4` or modiofy any files other than the ones in the `FEATURE_DIR/lean` folder.

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

3. Load and analyze the implementation context:
   - **REQUIRED**: Read tasks.md for the complete task list and execution plan
   - **REQUIRED**: Read plan.md for tech stack, architecture, and file structure
   - **IF EXISTS**: Read data-model.md for entities and relationships
   - **IF EXISTS**: Read contracts/ for API specifications and test requirements
   - **IF EXISTS**: Read research.md for technical decisions and constraints
   - **IF EXISTS**: Read quickstart.md for integration scenarios

5. Parse tasks.md structure and extract:
   - **Task phases**: Setup, Tests, Core, Integration, Polish
   - **Task dependencies**: Sequential vs parallel execution rules
   - **Task details**: ID, description, file paths, parallel markers [P]
   - **Execution flow**: Order and dependency requirements

6. Generate a Lean4 model based on the task plan:
   - **Task-by-Task execution**: For every task, generate a lean4 code that faithfully represents the task.
   - **Verify** Verify that the lean4 code is complete and can be validated
   - **Store** Once verification is complete, store the lean4 code in the `lean` directory with the appropriate naming conventions.

8. Progress tracking and error handling:
   - Report progress after each completed task
   - Halt execution if any non-parallel task fails
   - For parallel tasks [P], continue with successful tasks, report failed ones
   - Provide clear error messages with context for debugging
   - Suggest next steps if implementation cannot proceed
   - **IMPORTANT** For completed tasks, make sure to mark the task off as [X] in the tasks file.

Note: This command assumes a complete task breakdown exists in tasks.md. If tasks are incomplete or missing, suggest running `/speckit.tasks` first to regenerate the task list.
