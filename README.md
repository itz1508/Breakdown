# Breakdown

Breakdown is a Python system for controlled research, specification review, planning, sandboxed implementation, independent validation, and durable evidence retention.

## Package ownership

```text
breakdown/
├── __init__.py
├── __main__.py
├── tests/                         # Cross-agent, architecture and workflow tests
├── agents/                         # Shared source-grounded prompt assembly
│   ├── __init__.py
│   ├── prompt.py
│   └── WORKING_FRAMEWORK.md
├── shared/
│   ├── base.py
│   ├── config.py
│   ├── models.py
│   ├── model_loop.py
│   └── tests/
├── researcher/                    # agent.py, SKILL.md, tests/
├── auditor/                       # agent.py, SKILL.md, tests/
├── coder/                         # agent.py, SKILL.md, tests/
├── planner/                       # agent.py, SKILL.md, tests/
├── builder/                       # independent agent.py, SKILL.md, tests/
└── system/
    ├── runtime/
    ├── storage/
    ├── tools/
    ├── memory.py
    ├── safety.py
    └── tests/
```

The currently implemented agent packages are Researcher, Auditor, Coder, Planner, and Builder. Builder is a sibling package at `breakdown/builder/`; it uses the separate coding backend and does not use `shared/model_loop.py`. Discovery is part of the accepted six-agent target but is not yet implemented or registered on this branch. The executable workflow remains the current eight-stage `breakdown.yaml`; it has not yet been migrated to the Discovery-first target workflow.

## Authority boundaries

- `breakdown/__main__.py` is the composition root and creates the agent registry.
- `agents/` owns shared prompt assembly and the source-grounded working framework; each agent's colocated `SKILL.md` supplies its role-specific instructions.
- `shared/` owns shared types, strict model bases, configuration schema, and shared model-loop utilities.
- Each agent package owns its implementation, canonical `SKILL.md` instructions, and tests.
- `system/runtime/` owns workflow orchestration, authorization, lifecycle and execution control.
- `system/storage/` owns durable storage and checkpoint/digest mechanisms.
- `system/tools/` owns canonical system tools and role-scoped tool access.
- `system/safety.py` and `system/memory.py` own safety and memory behavior.
- Root `docs/`, `evals/`, `scripts/`, `pyproject.toml`, and `uv.lock` remain repository-level resources.

Runtime is the authority for progression and source effects. Agents return bounded work and evidence; they do not self-advance workflow state or authorize synchronization.

## Live model tiers

Live builds require a dedicated verifier model distinct from the Builder model:
`BREAKDOWN_MODEL_BUILDER` and `BREAKDOWN_MODEL_VERIFIER`. The verifier is a separate evaluation invocation; if it is missing, unavailable, or returns an incomplete/non-valid result, synchronization is blocked. A configured verifier does not replace execution of validation commands: command-based checks require actual execution output before they can be accepted.

## Development

```bash
uv sync --locked
uv run --no-sync python -m compileall breakdown evals scripts
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy breakdown
uv run --no-sync python evals/run.py --offline
```

Live model, sandbox, and external-provider behavior must be verified separately from offline tests. Report only commands that were actually run and the evidence they produced.
