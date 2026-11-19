# OneShot Breakdown

A contract-driven, eight-stage workflow engine: one user request becomes a
researched, approved, sandboxed, and synchronized change — with every step
durable, auditable, and bounded by a deterministic safety boundary.

`breakdown.yaml` is the sole workflow definition. Stages are contracts
(role / decision / deterministic); roles own one SDK-native chain each and
never persist artifacts or advance the workflow; the runtime owns
progression, budget, recovery, approvals, and synchronization.

## Stages

1. `research_proposal` (auditor) → 2. `research_approval` (user) →
3. `research_execution` (researcher) → 4. `findings_review` (auditor) →
5. `implementation_planning` (planner, then deterministic freeze +
preflight) → 6. `plan_approval` (user) → 7. `build_execution` (builder in
a sandbox; deterministic detect → authorize → synchronize) →
8. `completion` (deterministic, accepts-matrix validated).

## Quickstart

```bash
uv sync --locked

# Validate definition + contract alignment (offline)
uv run --no-sync python -m breakdown --check

# Offline demo run against a scratch target (no model SDK needed)
mkdir demo-target && cd demo-target
uv run --no-sync python -m breakdown run "Create the demo change record" \
    --workflow ../breakdown.yaml --target . --offline-demo
# prints: state awaiting_decision, stage research_approval, run: <id>

uv run --no-sync python -m breakdown decide <id> approve --workflow ../breakdown.yaml --target . --offline-demo
uv run --no-sync python -m breakdown resume <id> --workflow ../breakdown.yaml --target . --offline-demo
uv run --no-sync python -m breakdown decide <id> approve --workflow ../breakdown.yaml --target . --offline-demo
uv run --no-sync python -m breakdown resume <id> --workflow ../breakdown.yaml --target . --offline-demo
uv run --no-sync python -m breakdown status <id> --workflow ../breakdown.yaml --target .
# DEMO_CHANGE.md is synchronized into the target; status prints the Markdown report
```

Commands: `run`, `resume`, `decide`, `cancel`, `status`, `--check`.
Mutating commands require `--offline-demo` while Phase 2 ships no live SDK
backends. State lives in `<target>/.breakdown/` (SQLite stores, gitignored);
a lockfile guards concurrent access (`--force-unlock` takes over a
known-stale lock). Every invocation is stateless — runs pause at approvals
and resume in later processes.

## Development

```bash
uv run --no-sync pytest -q          # tests (uses --basetemp=.pytest-tmp)
uv run --no-sync ruff check .       # lint
uv run --no-sync ruff format .      # format
uv run --no-sync mypy breakdown     # strict types
uv run --no-sync python evals/run.py --offline   # blocking-zero evals
```

The offline evals score all eight blocking zeros: five through role
contracts and semantic validators, three (`builder_unexpected_paths`,
`builder_authoritative_repo_writes`, `builder_unauthorized_synchronization`)
through the real safety boundary with scripted side-effect backends. A zero
with no exercising case fails the run — zeros are proven or failing, never
silently passing. See `evals/README.md`.

## Layout

- `breakdown/` — models, contracts, engine, stores (artifacts/events/runs),
  canonical serialization, checkpoint, safety boundary, approvals,
  planning/completion ops, reports, roles, demo backends, CLI.
- `breakdown.yaml` — the workflow definition (def-1 seed).
- `tests/` — pytest suite. `evals/` — offline blocking-zero evaluation.
- `PLANS.md` — execution plan and milestone record. `AGENTS.md` — agent
  operating instructions.
