---
name: brainstorming
description: Use when creating or developing, before writing code or implementation plans - refines rough ideas into fully-formed designs through collaborative questioning, alternative exploration, and incremental validation. Don't use during clear 'mechanical' processes
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).
You **MUST** use the configured MCP servers. use context7.
You **MUST** respect the ground rules established at `.specify/memory/constitution.md`.

# Brainstorming Ideas Into Designs

## Overview

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design in small sections (200-300 words), checking after each section whether it looks right so far.

## Build knowledge

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. Load and analyze the implementation context:
   - **REQUIRED**: Read tasks.md for the complete task list and execution plan
   - **REQUIRED**: Read plan.md for tech stack, architecture, and file structure
   - **IF EXISTS**: Read data-model.md for entities and relationships
   - **IF EXISTS**: Read contracts/ for API specifications and test requirements
   - **IF EXISTS**: Read research.md for technical decisions and constraints
   - **IF EXISTS**: Read quickstart.md for integration scenarios

## The Process

**Understanding the idea:**
- Check out the current project state first (files, docs, recent commits)
- Ask questions one at a time to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Only one question per message - if a topic needs more exploration, break it into multiple questions
- Focus on understanding: purpose, constraints, success criteria

**Exploring approaches:**
- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why

**Presenting the design:**
- Once you believe you understand what you're building, present the design
- Break it into sections of 200-300 words
- Ask after each section whether it looks right so far
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and clarify if something doesn't make sense

## After the Design

**Documentation:**
- Write the validated design to `tmp/FEATURE_DIR/DD-MM-YYYY-<topic>-design.md`.
- Use `superpowers:writing-skills` skill if available.
- Commit this design document to git.

## Update Feature Specification

- **IMPORTANT** Follow the structure of the file and do not regenerate, but modify.
- Propose updates to `FEATURE_DIR/spec.md` with the summaries of any changes as follows:
    - Suggest minimal changes required to capture the result of the brainstorming.
    - New sections can be introduced, if required.
- Present the changes as a diff and ask for confirmation before proceeding with update.
- If changes are rejected by the user, store them under `tmp/FEATURE_DIR/DD-MM-YYY-<topic>-spec.md`; otherwise update `FEATURE_DIR/spec.md`.

## Update Implementation Plan

- **IMPORTANT** Follow the structure of the file and do not regenerate, but modify.
- Propose updates to `FEATURE_DIR/plan.md` with the summaries of any changes as follows:
    - Suggest minimal changes required to capture the result of the brainstorming.
    - New sections can be introduced, if required.
- Present the changes as a diff and ask for confirmation before proceeding with update. Use colouring and highlight changed words.
- If changes are rejected by the user, store them under `tmp/FEATURE_DIR/DD-MM-YYY-<topic>-plan.md`; otherwise update `FEATURE_DIR/plan.md`.

## Update task definitions

**Task updates**
- List all tasks affected by the brainstorming session.
- For each task display the changes proposed as a diff as follows:
    - Take the existing task definition as is. **IMPORTANT** The first sentence should remain unchanged (unless there are fundamental changes).
    - Apply the clarifications from the brainstorming session to the line.
    - Reference all relevant functional requirements by identifier, like `FR-XXX`.
- Present the changes as a diff and ask for confirmation before proceeding with update. Use colouring and highlight changed words.
- If changes are rejected by the user, store them under `tmp/FEATURE_DIR/DD-MM-YYY-<topic>-tasks.md`; otherwise update the `FEATURE_DIR/tasks.md`.

## Update contract

- **IMPORTANT** Follow the structure of the file and do not regenerate, but modify.
- Propose updates to all `FEATURE_DIR/contracts/<contract_file>` with the summaries of any changes as follows:
    - Suggest minimal changes required to capture the result of the brainstorming.
    - New sections can be introduced, if required.
- Present the changes as a diff and ask for confirmation before proceeding with update. Use colouring and highlight changed words.
- If changes are rejected by the user, store them under `tmp/FEATURE_DIR/DD-MM-YYY-<topic>-<contract_file>.md`; otherwise update `FEATURE_DIR/contracts/<contract_file>`.

## Key Principles

- **One question at a time** - Don't overwhelm with multiple questions.
- **Multiple choice preferred** - Easier to answer than open-ended when possible.
- **YAGNI ruthlessly** - Remove unnecessary features from all designs.
- **KISS ruthlessly** - If it is complicated, it must be wrong.
- **Explore alternatives** - Always propose 2-3 approaches before settling.
- **Incremental validation** - Present design in sections, validate each.
- **Be flexible** - Go back and clarify when something doesn't make sense.

