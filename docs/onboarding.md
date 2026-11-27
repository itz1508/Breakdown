# Onboarding

## Repository setup

1. Clone the repository and inspect `AGENTS.md`.
2. Install the locked development environment with `uv sync --locked`.
3. Read [Architecture](architecture.md) and [Current Architecture and Workflow](current-architecture-workflow.md).
4. Locate the owning package before changing behavior.

## Package orientation

- `breakdown/__main__.py`: sole composition root and agent registry.
- `breakdown/shared/`: shared models, strict base, configuration schema and model-loop helpers.
- `breakdown/researcher/`, `auditor/`, `coder/`, `planner/`: independent agent packages.
- `breakdown/builder/`: independent Builder package; receives the shared working framework and its local skill, and does not use the shared model loop.
- `breakdown/agents/`: common prompt assembly and source-grounded agent working framework.
- `breakdown/system/runtime/`: host-controlled runtime.
- `breakdown/system/storage/`: durable records and checkpoint/digest implementation.
- `breakdown/system/tools/`: canonical tools and scoped dispatch.
- `breakdown/system/safety.py`, `memory.py`: system safety and memory owners.

Each agent's `SKILL.md` is colocated with its `agent.py`. Do not maintain duplicate instruction text in another prompt constant or root skill file.

## Local verification

```bash
uv run --no-sync python -m compileall breakdown evals scripts
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy breakdown
uv run --no-sync python evals/run.py --offline
```

These commands are repository checks, not proof of live model-provider behavior or production sandbox execution. Record which commands actually ran and preserve their outputs/evidence.
