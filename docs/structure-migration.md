# Package Structure Migration

## Target

The active package layout is recorded in [Current Architecture and Workflow](current-architecture-workflow.md). The intended package ownership is:

- `shared/`: base, models, configuration and model-loop support
- `researcher/`, `auditor/`, `coder/`, `planner/`: independent agent packages
- `planner/builder/`: Builder package; no shared model loop
- `system/runtime/`: runtime orchestration and backend wiring
- `system/storage/`: persistence and checkpoint/digest owners
- `system/tools/`: canonical tools and role-scoped dispatch
- `system/safety.py`, `system/memory.py`: safety and memory

Each agent package owns `agent.py`, `SKILL.md`, and `tests/`. Cross-agent and workflow tests remain in `breakdown/tests/`; system behavior tests live in `breakdown/system/tests/`; shared-model tests live in `breakdown/shared/tests/`.

## Repository-level paths

The following remain at the repository root: `docs/`, `evals/`, `scripts/`, `breakdown.yaml`, `pyproject.toml`, `uv.lock`, `AGENTS.md`, and `README.md`.

## Migration invariants

1. `breakdown/__main__.py` is the only composition root and constructs the agent registry.
2. Coder is independent and is not injected into Auditor as a sub-role.
3. Builder is separate from Planner's implementation and does not import or invoke the shared model loop.
4. Runtime owns progression, permissions, approvals, resume/cancel, and source effects.
5. Storage has one owner per durable record family; no duplicate store or registry is introduced.
6. Tests are moved without deleting or weakening assertions.
7. All imports, tests, evals, scripts, docs and configuration consumers must use the new owners.
8. Retired module and skill paths are removed only after no active references remain.

## Verification

After relocation, run compileall, import smoke tests, pytest, Ruff, mypy and offline evals. These commands establish only the behavior they actually exercise; package structure alone does not establish end-to-end workflow correctness.
