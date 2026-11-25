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
Mutating commands need a backend source: `--offline-demo` (scripted, no
API) or `--live` (OpenAI-compatible API). State lives in
`<target>/.breakdown/` (SQLite stores, gitignored); a lockfile guards
concurrent access (`--force-unlock` takes over a known-stale lock). Every
invocation is stateless — runs pause at approvals and resume in later
processes.

## Live mode (Databricks key or any custom API key)

The live backends speak any OpenAI-compatible chat API — Databricks Model
Serving, a custom gateway (LiteLLM/vLLM/Ollama-style), or OpenAI itself.
Set the environment (see `.env.example`):

```bash
# Databricks Model Serving
export BREAKDOWN_API_BASE_URL="https://<workspace-url>/serving-endpoints/<endpoint-name>/v1"
export BREAKDOWN_API_KEY="<databricks-pat>"
export BREAKDOWN_MODEL="<served-model-name>"
# Optional two-tier economics: frontier for judgment, cheaper for reading
export BREAKDOWN_MODEL_AUDITOR="<frontier-model>"
export BREAKDOWN_MODEL_RESEARCHER="<cheap-model>"
```

Live runs are binding-gated: first produce evaluation evidence, then
record bindings (template: `bindings.example.json`):

```bash
uv run --no-sync python scripts/live_probe.py          # endpoint smoke test
uv run --no-sync python evals/run.py --live            # role evaluation against the live API
# record BackendBinding records from the evaluation, then:
uv run --no-sync python -m breakdown run "your request" \
    --workflow breakdown.yaml --target <repo> --live --bindings bindings.json
```

Cost attribution is per stage: `status` renders a stage-cost table, the
completion record carries `cost_summary.by_stage`, and budget exhaustion
records which stage spent what.

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

## Documentation

The documentation is organized by audience:

- [Documentation index](docs/README.md)
- [Architecture and integration points](docs/architecture.md)
- [Workflow and data flow](docs/workflow.md)
- [Onboarding and environment setup](docs/onboarding.md)
- [Operations and common walkthroughs](docs/operations.md)
- [Development and verification](docs/development.md)

These guides describe the current implementation on main. The separate
[current architecture/workflow proposal](docs/current-architecture-workflow.md)
describes a target direction and must not be mistaken for deployed behavior.

## Layout

- `breakdown/` — models, contracts, engine, stores (artifacts/events/runs),
  canonical serialization, checkpoint, safety boundary, approvals,
  planning/completion ops, reports, roles, demo backends, CLI.
- `breakdown.yaml` — the workflow definition (def-1 seed).
- `tests/` — pytest suite. `evals/` — offline blocking-zero evaluation.
- `PLANS.md` — execution plan and milestone record. `AGENTS.md` — agent
  operating instructions.

## Independent Verification

Synchronization authorization today depends on an independent verifier — a separate model invocation in a fresh context that receives only the rubric (the plan's `validation_steps` and `expected_result` strings) and the actual sandbox file contents, and returns per-criterion verdicts. The builder's self-report (`validation_results`) remains stored as evidence but no longer gates authorization.

After this change, if a verifier backend is configured (via `BREAKDOWN_MODEL_VERIFIER` in `.env`), `integration_valid` inside `_post_build` is computed from the verifier's per-criterion results. If no verifier is configured, the legacy self-report path is used unchanged, preserving backward compatibility for eval fakes and existing test harnesses.

A human can observe this behavior from the command line: a builder may claim success while the run ends `failed` because the verifier reported `not_valid` for one criterion, or the target repository contains none of the sandbox-produced files when verification rejects.

## Cross-Run Memory

Completed runs leave durable memory behind in the target's `.breakdown/state/memory.db`. The engine writes deterministic lesson documents on run completion: `runs/<run_id>.md` for successful runs and `lessons/<run_id>.md` for failed or cancelled runs. These markdown documents are immutable versions — the input store is never modified.

Three canonical tools let roles read past lessons:

- `memory list [--prefix P]` — list lesson documents by path prefix
- `memory show PATH [--revision N]` — show a specific revision of a lesson document (read-only, no lock)
- `memory search PATTERN` — regex search against lesson document content

A live-only `consolidate-memory --live [--instructions TEXT]` command merges accumulated lessons into a fresh revision without ever modifying the inputs. Without `--live`, the command prints a refusal explaining consolidation requires a live model and exits nonzero.

Lesson documents can be inspected with `python -m breakdown memory list --target <target>` and `python -m breakdown memory show runs/<run_id>.md --target <target>`.
