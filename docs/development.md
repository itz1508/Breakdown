# Development Guide

For contributors changing Breakdown itself.

## Repository workflow

1. Read AGENTS.md and the relevant current architecture/workflow documents.
2. Inspect the physical source, tests and breakdown.yaml before proposing paths or APIs.
3. Identify the smallest change and its protected behavior.
4. For implementation work, record the approved task scope and key decisions in the associated GitHub pull request and relevant design/migration document. Documentation-only maintenance does not require a separate progress entry.
5. Implement against existing models, contracts, stores and capability interfaces.
6. Add or update tests and offline evaluations for the behavior changed.
7. Run the verification commands below.
8. Update documentation affected by the change. Record actual implementation progress, evidence-backed discoveries, decisions, verification, and outcomes in the associated pull request and commit history. Do not create a separate root-level planning journal or turn documentation-only maintenance into a retroactive execution log.
9. Report commands actually run and any remaining not-run checks.

Workflow-execution agents must not edit AGENTS.md, breakdown.yaml, or .breakdown/ during a normal workflow run.

## Source map for common changes

| Change | Inspect and update |
|---|---|
| Add or change a workflow stage | breakdown.yaml, models.py operation input/output models, contracts.py registry and mapper, engine behavior, tests/test_workflow.py, tests/test_contracts.py and tests/test_definition_consistency.py |
| Change role behavior | Relevant module in breakdown/roles/, its typed models and backend request, role tests, stage contracts and evals/cases |
| Add a canonical tool | breakdown/tools.py typed input/output, canonical registry, role allowlists, dispatch path, tool tests and role behavior tests |
| Change backend integration | breakdown/live_backend.py, bootstrap.py, bindings.py, .env.example, live-backend tests and live evaluation |
| Change sandbox or synchronization policy | breakdown/safety.py, checkpoint.py, breakdown.yaml authorization/synchronization declarations, safety tests and safety eval cases |
| Change approvals or completion | approvals.py, completion.py, engine.py, breakdown.yaml decision/terminal rules and lifecycle tests |
| Change persistence | Owning store module, models.py, event/run/artifact tests and recovery behavior |

Do not introduce a second model, store, registry or capability implementation before checking whether an existing one covers the requirement.

## Local verification

Run from the repository root:

    uv run --no-sync python -m breakdown --check
    uv run --no-sync pytest -q
    uv run --no-sync ruff check .
    uv run --no-sync ruff format --check .
    uv run --no-sync mypy breakdown
    uv run --no-sync python evals/run.py --offline

The test configuration uses a project-local .pytest-tmp directory. Do not delete or edit test cases merely to obtain a clean result.

## Offline evaluations

The evaluation harness has two types of cases:

- Role cases use scripted backend payloads to test typed output acceptance and rejection.
- Safety cases run a scripted Builder inside a real temporary sandbox and exercise independent changed-path detection and synchronization authorization.

The offline harness proves local contracts and deterministic safety behavior. It does not prove live model judgment, endpoint compatibility, production deployment, or a real user's repository outcome.

## Style and review

The project config in pyproject.toml is authoritative. It currently targets Python 3.11 and uses Ruff with a 120-character line length and strict mypy configuration for the Breakdown package.

Review changed files for:

- Correctness and task completion.
- Reliability and explicit failure handling.
- Groundedness: source evidence, capability reuse, and traceable decisions.
- Security: tool allowlists, path containment, secret handling, approvals and synchronization scope.
- Cost and latency: record actual usage; do not weaken evidence or authorization to optimize a metric.

## Target architecture note

The latest four-agent target architecture and project work tree are recorded in docs/current-architecture-workflow.md; the source-owner map, workflow/schema migration, and consolidation gates are in docs/structure-migration.md. Current source still has the flat `breakdown/` package, `breakdown/roles/`, top-level `agents/skills/`, root `tests/`, and the executable eight-stage `breakdown.yaml`. Keep those current consumers intact until the new definitions/runtime are wired; the target workflow is a separate behavior migration, not just a package move.
