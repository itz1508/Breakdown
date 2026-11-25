# Breakdown Documentation

This documentation is organized by audience and task. It describes the implementation currently present on the repository's main branch unless a page is explicitly labelled as a proposal.

## Start here

| Audience | Read |
|---|---|
| New operator or contributor | [Onboarding](onboarding.md) |
| Architect or maintainer | [Architecture](architecture.md) |
| Workflow author or reviewer | [Workflow and data flow](workflow.md) |
| Developer changing code | [Development guide](development.md) |
| Operator running or recovering a workflow | [Operations guide](operations.md) |

## Context and source of truth

Breakdown is a contract-driven Python workflow engine. A request is processed through a declarative workflow, typed role operations, recorded user decisions, durable artifacts, a checkpointed sandbox build, and evidence-based completion.

When documentation conflicts with the implementation, use this authority order:

1. Current source code, runtime behavior, tests, and configuration describe what is implemented.
2. breakdown.yaml defines the executable workflow and its declared ownership, transitions, artifacts, budgets, and validation rules.
3. PLANS.md is the living implementation ExecPlan and records evidence from work actually executed; it is not a generic activity log.
4. AGENTS.md contains the repository's standing rules for workflow-execution agents.
5. Design documents describe proposed changes only when they explicitly say so.

The document [current-architecture-workflow.md](current-architecture-workflow.md) is the **latest four-agent target architecture and workflow**. It is not the currently deployed workflow or package layout. [structure-migration.md](structure-migration.md) records the source-owner map and migration sequence; [structure-gap-review.md](structure-gap-review.md) records the gap review. `docs/workflow.md` describes the executable eight-stage workflow on `main`.

## Keep documentation maintainable

- Update the relevant audience page when a command, setting, interface, ownership boundary, or operational behavior changes.
- Link to source files instead of copying long implementation details.
- Use exact commands from the project configuration and CLI.
- Mark behavior as implemented, proposed, or unverified. Never describe a target tree as the current source tree.
- Keep PLANS.md as the living project record. Do not add a competing progress file.
