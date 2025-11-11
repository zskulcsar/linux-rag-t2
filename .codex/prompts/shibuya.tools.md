---
description: Check required tools for the implementation plan by processing and executing all tasks defined in tasks.md
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).
You **MUST** use the configured MCP servers. use context7.

## Operating contraints

**STRICTLY READ-ONLY**: Do **not** modify any files other than `specs/FEATURE_DIR/dependencies.md`. Output a structured analysis report.

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. Load and analyze the implementation context:
   - **REQUIRED**: Read tasks.md for the complete task list and execution plan
   - **REQUIRED**: Read plan.md for tech stack, architecture, and file structure
   - **IF EXISTS**: Read data-model.md for entities and relationships
   - **IF EXISTS**: Read contracts/ for API specifications and test requirements
   - **IF EXISTS**: Read research.md for technical decisions and constraints
   - **IF EXISTS**: Read quickstart.md for integration scenarios

3. Parse tasks.md structure and extract:
   - **Task phases**: Setup, Tests, Core, Integration, Polish
   - **Task dependencies**: Sequential vs parallel execution rules
   - **Task details**: ID, description, file paths, parallel markers [P]
   - **Execution flow**: Order and dependency requirements

4. Plan the implementation:
   - **REQUIRED** create a plan of implementation as follows:
      * **Phase-by-phase planning**: List each phase before moving to the next
      * **Respect dependencies**: Plan sequential tasks in order, parallel tasks [P] can run together
      * **Follow TDD approach**: Plan test tasks before their corresponding implementation tasks
      * **File-based coordination**: Tasks affecting the same files must be planned sequentially
      * **Validation checkpoints**: Plan verification for each phase completion before proceeding
     **IMPORTANT**: You must not make any modifications, just plan the implementation.

5. Check the existence of tools and development dependencies
   - **Check** Check if the `dependencies.md` file at `specs/FEATURE_DIR` is present.
   - **Verify** Verify if the tool or development dependency exist on the system. If the `dependencies.md` is listing different status for the tool than the verified status, update the file.
   - **Report** create a tool report table and show it to the user:
     ```markdown
     | Task ID | Required tool/dependency | Status | Installation command |
     |---------|--------------------------|--------|----------------------|
     | T001    | gcc                      | Not available | `sudo apt install gcc` |
     | T001    | uv                       | Present | N/A |
     | T002    | go                       | Present | N/A |
     ```
   - Create a file `specs/FEATURE_DIR/dependencies.md` and output the report there.

Note: This command assumes a complete task breakdown exists in tasks.md. If tasks are incomplete or missing, suggest running `/speckit.tasks` first to regenerate the task list.
