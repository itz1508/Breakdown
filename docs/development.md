# Development Guide

## Change process

1. Read `AGENTS.md` and the current architecture/workflow documents.
2. Inspect the physical source, tests, evals, scripts and configuration before changing ownership.
3. Make the smallest complete change and preserve existing behavior unless a behavior migration is explicitly part of scope.
4. Keep one source owner for each responsibility. Do not add duplicate models, stores, registries, workflow authorities or configuration sources.
5. Update colocated tests and cross-package tests. Preserve assertions during test relocation.
6. Update docs, evals, scripts and package configuration affected by the change.
7. Run compileall, pytest, Ruff, mypy and offline evals where applicable. Report the commands actually run.

## Source map

| Change | Primary owner |
|---|---|
| Cross-agent types and strict base | `breakdown/shared/base.py`, `breakdown/shared/models.py` |
| Configuration schema/access | `breakdown/shared/config.py` |
| Shared structured model loop | `breakdown/shared/model_loop.py` |
| Agent behavior and instruction changes | Its package's `agent.py` and `SKILL.md`; shared prompt assembly in `breakdown/agents/prompt.py` |
| Workflow progression and approvals | `breakdown/system/runtime/` |
| Artifact/event/run/checkpoint persistence | `breakdown/system/storage/` |
| Canonical tools and tool dispatch | `breakdown/system/tools/` |
| Path containment and source effects | `breakdown/system/safety.py` |
| Memory | `breakdown/system/memory.py` |

Builder is located at `breakdown/builder/`, outside Planner, and must not depend on `shared/model_loop.py`. It receives the common framework and Builder skill through `CodingBackendRequest.agent_instructions`.

## Verification commands

```bash
uv run --no-sync python -m compileall breakdown evals scripts
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy breakdown
uv run --no-sync python evals/run.py --offline
```
