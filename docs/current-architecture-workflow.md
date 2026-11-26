# Breakdown — Current Target Architecture

**Target package:** `breakdown/`  
**Agent model:** five independent agent packages, with Builder nested under Planner's package path.

## 1. Operating boundaries

- The user supplies intent and makes the decisions that require user authority.
- `__main__.py` is the sole composition root and constructs the agent registry.
- Agents perform bounded work and return typed results and evidence. They do not own workflow progression, approvals, durable storage, or synchronization authority.
- `shared/` owns common models, base abstractions, configuration schema, and shared model-loop utilities.
- `system/runtime/` owns orchestration and lifecycle; `system/storage/` owns persistence; `system/tools/` owns canonical tools.
- `system/safety.py` owns safety enforcement; `system/memory.py` owns memory behavior.
- Each agent's `SKILL.md` is colocated with its implementation and is the canonical instruction source for that package.

## 2. Agent packages

| Agent | Package path | Responsibility boundary |
|---|---|---|
| Researcher | `breakdown/researcher/` | Investigates accepted research items and preserves provenance, contradictions and unknowns. |
| Auditor | `breakdown/auditor/` | Prepares and checks specifications; compares findings against repository evidence. |
| Coder | `breakdown/coder/` | Independent bounded code-analysis role; not an Auditor-owned sub-role. |
| Planner | `breakdown/planner/` | Owns planning decisions, work decomposition, gap analysis and the confirmed task package. |
| Builder | `breakdown/planner/builder/` | Executes only the confirmed work in the authorized sandbox; does not use the shared model loop. |

Each agent package contains `__init__.py`, `agent.py`, `SKILL.md`, and `tests/`. The Builder package is intentionally located beneath Planner's package path as shown above; its runtime identity remains Builder.

## 3. Workflow target

1. Session start or resume and user input.
2. Auditor prepares the specification as a revisioned `discovery.json`.
3. The user reviews the revision-preserving edit preview. Agent edits, manual edits, and detail additions/removals retain prior revisions.
4. Decline records the decision and completes without Build. Accept & Check asks Auditor to validate the exact accepted specification. Material issues return to clarification/edit; changed content must be reviewed and accepted again.
5. Researcher investigates accepted research items.
6. Auditor compares research findings with repository evidence.
7. Planner prepares the project/phase/task decomposition, resolves planning gaps, and prepares the exact package.
8. User confirmation binds the exact package revision and source checkpoint.
9. Builder verifies the binding, executes the confirmed work in the authorized sandbox, exports the result, and exits.
10. Independent validation evaluates the exported result. Completion retains evidence and the outcome.

A task's To-do is a small guidance sequence for one task, not a deferred scheduler. Dependencies determine ordering; independent tasks may proceed concurrently where the workflow and host permit. Builder remains sequential within its confirmed execution.

## 4. Validation and authority

- Approval binds the exact accepted revision, plan/package digest, source checkpoint, run/session context, user identity and timestamp.
- A changed specification invalidates its prior acceptance. A changed package requires new confirmation.
- Builder cannot add, reorder, or skip confirmed tasks.
- Runtime owns sandbox lifecycle and synchronization authorization.
- Independent validation does not consume Builder's self-reported validation as proof.
- Completion claims are limited to retained, inspectable evidence.

## 5. Repository structure

```text
breakdown/
├── __init__.py
├── __main__.py
├── tests/
├── shared/
│   ├── __init__.py
│   ├── base.py
│   ├── config.py
│   ├── models.py
│   ├── model_loop.py
│   └── tests/
├── researcher/
│   ├── __init__.py
│   ├── agent.py
│   ├── SKILL.md
│   └── tests/
├── auditor/
│   ├── __init__.py
│   ├── agent.py
│   ├── SKILL.md
│   └── tests/
├── coder/
│   ├── __init__.py
│   ├── agent.py
│   ├── SKILL.md
│   └── tests/
├── planner/
│   ├── __init__.py
│   ├── agent.py
│   ├── SKILL.md
│   ├── tests/
│   └── builder/
│       ├── __init__.py
│       ├── agent.py
│       ├── SKILL.md
│       └── tests/
└── system/
    ├── __init__.py
    ├── runtime/
    ├── storage/
    ├── tools/
    ├── memory.py
    ├── safety.py
    └── tests/
```

The repository-level `docs/`, `evals/`, `scripts/`, `breakdown.yaml`, `pyproject.toml`, `AGENTS.md`, and `README.md` remain outside the Python package.
