# Breakdown Package Consolidation Plan

**Date:** 2026-11-25  
**Repository:** `itz1508/Breakdown`  
**Baseline branch:** `main`  
**Baseline commit:** `71218fe820208ff3b5e6118ea5c017568f7a5a73`  
**Working branch:** `migration/latest-four-agent-layout`  
**Status:** source inventory and migration plan; Python source has not yet been moved in this first slice.

## Objective

Consolidate the current flat `breakdown/` package and top-level `agents/skills/` documentation into the four-agent package layout in [current-architecture-workflow.md](current-architecture-workflow.md). Preserve executable behavior, persistence formats, workflow semantics, and tests while changing ownership and import paths. Delete legacy paths only after their contents and references have been migrated and the relevant checks have run.

## Repository evidence at baseline

The repository currently contains:

- `breakdown/models.py`, `contracts.py`, `engine.py`, `bootstrap.py`, `roles/`, and the remaining flat runtime/store/tool modules.
- `agents/skills/{auditor,builder,coder,planner,researcher}/SKILL.md` at repository root.
- Root `tests/`, including role, contract, engine, persistence, safety, workflow, and CLI coverage.
- Root `evals/` and `scripts/` that import the current `breakdown.*` namespace.
- `breakdown.yaml` with role-guidance paths that still refer to the old top-level `agents/skills/` tree.
- `pyproject.toml` packaging and tool configuration tied to the current `breakdown` package and root `tests/`.

The imports are coupled across runtime modules, roles, tests, evals, scripts, and documentation. The legacy package cannot be deleted as a directory-only cleanup.

## Source-owner migration map

This map records the initial destination by responsibility. Exact split points and final filenames must be checked against all imports and public interfaces before each move.

| Current source owner | Target owner | Migration treatment |
|---|---|---|
| `breakdown/models.py` | `breakdown/shared/{base,models,config}.py` | Split strict base, cross-agent Pydantic models, and settings/configuration; preserve serialized field names and schema behavior. |
| `breakdown/contracts.py` | `breakdown/shared/` and `breakdown/system/runtime/` | Split shared protocols/types from runtime activation, registry generation, mapping, and workflow-dependent validation. Do not create a separate `contracts/` directory. |
| `breakdown/roles/__init__.py` | `breakdown/agents/loop.py` | Move shared structured-output validation, prompt rendering, and injected role-tool access; retain least-privilege behavior. |
| `breakdown/roles/auditor.py` | `breakdown/agents/auditor/agent.py` | Consolidate Auditor definition and implementation. |
| `breakdown/roles/coder.py` | `breakdown/agents/auditor/coder.py` | Preserve as an Auditor-owned, read-only capability, not an independently dispatched agent. |
| `breakdown/roles/researcher.py` | `breakdown/agents/researcher/agent.py` | Consolidate Researcher definition and implementation. |
| `breakdown/roles/planner.py` | `breakdown/agents/planner/agent.py` | Consolidate Planner definition and implementation. |
| `breakdown/roles/builder.py` | `breakdown/agents/builder/agent.py` | Consolidate Builder definition and implementation. |
| `agents/skills/*/SKILL.md` | Each agent's YAML module docstring | Merge the canonical instructions once. Remove manually maintained duplicates after consumers and tests use the docstring. |
| `breakdown/engine.py`, `approvals.py`, `planning_ops.py`, `completion.py`, `verification.py`, `bootstrap.py`, `bot.py`, `reports.py` | `breakdown/system/runtime/` | Move runtime-owned behavior; inject agent instances from `__main__.py`; Runtime must not import agent modules. |
| `breakdown/artifact_store.py`, `events.py`, `run_store.py`, `checkpoint.py`, `canonical.py` | `breakdown/system/storage/` | Move existing persistence/digest owners without adding a second store or changing durable formats. |
| `breakdown/tools.py`, `semantic_search.py` | `breakdown/system/tools/` | Move canonical tool definitions and handlers, preserving role allowlists and dispatch checks. |
| `breakdown/safety.py` | `breakdown/system/safety.py` | Preserve path containment, sandbox integrity, changed-path detection, and synchronization authorization. |
| `breakdown/memory.py` | `breakdown/system/memory.py` | Preserve the existing cross-run memory owner; do not create another persistence backend. |
| `breakdown/bindings.py`, `live_backend.py`, `demo.py` | `breakdown/system/runtime/` (exact sub-ownership to verify) | Preserve provider binding validation and live/offline backend selection; do not invent a provider abstraction. |
| Root `tests/` | Agent-local, `shared/tests/`, `system/tests/`, and `breakdown/tests/` | Move tests beside their owners. Keep only layering, cross-agent contract, and workflow-level tests at package root. Never weaken or delete assertions to accommodate a move. |
| `evals/`, `scripts/`, `breakdown.yaml`, `pyproject.toml` | Existing repository-level locations, updated in place | Update imports, role-guidance references, packaging, tool/test configuration, and verified commands after target modules exist. |

The target tree does not prescribe a new `host/` or `contracts/` directory. Keep Runtime as the workflow authority in this revision. Do not create additional schedulers, queues, agents, stores, or entry points.

## Migration phases

### Phase 0 — Baseline and target contract

- Pin the source commit and record current paths, active imports, settings, entry points, tests, and workflow definition.
- Publish the target tree, agent ownership rules, static YAML-definition rules, and migration map.
- Keep `main` unchanged while the migration is reviewed.

### Phase 1 — Shared contracts and configuration

- Split `StrictModel`, cross-agent Pydantic models, and settings into `shared/base.py`, `shared/models.py`, and `shared/config.py`.
- Separate shared protocol/types from runtime contract activation without creating an extra `contracts/` directory.
- Move and update focused shared-contract tests; verify AST layering and import direction.

### Phase 2 — Agent consolidation

- Move the four agent implementations into their owning folders; move Coder under Auditor.
- Merge each role's current SKILL guidance and implementation prompt into one canonical YAML docstring per dispatched agent.
- Add import-free AST discovery, first-statement/docstring checks, duplicate-YAML-key rejection, strict Pydantic validation, folder/id matching, and static shared-contract reference validation.
- Put agent-specific tests in each agent folder. Remove old skill/role paths only after imports and tests point to the new owners.

### Phase 3 — Runtime, Storage, tools, safety, and memory

- Move runtime orchestration and approval/plan/completion behavior under `system/runtime/`.
- Move existing durable stores and digest/checkpoint owners under `system/storage/`.
- Move canonical tools under `system/tools/`; retain the existing permission allowlists.
- Move safety and memory to their designated `system/` owners.
- Keep `system/` independent of agent imports; inject the constructed agent set from the composition root.

### Phase 4 — Composition root and repository consumers

- Make `breakdown/__main__.py` the sole composition root that constructs the four agents and passes them to Runtime.
- Update all imports in package code, tests, evals, scripts, and documentation.
- Update `breakdown.yaml` role-guidance references so no executable configuration points at retired files.
- Update `pyproject.toml` package discovery, test paths, lint exclusions, and strict type-check paths from actual package layout.

### Phase 5 — Legacy removal and consolidation gate

Remove a legacy file or directory only after all of the following are true:

1. Its behavior and required instructions have an identified target owner.
2. All runtime, tests, evals, scripts, config, docs, and import references use the target owner.
3. No remaining code path imports the legacy module or reads its old skill path.
4. Focused owner tests and cross-boundary tests pass.
5. Full offline verification passes and the resulting diff shows no lost behavior or unexplained test reduction.

Then remove the retired `breakdown/roles/`, the old top-level `agents/skills/` tree, migrated flat modules, and root tests that have been relocated. Retain root-level `evals/`, `scripts/`, and repository manifests unless source evidence justifies another owner.

## Required verification

Use commands verified from the repository configuration after the migration is materialized:

```bash
uv run --no-sync python -m compileall breakdown evals scripts
uv run --no-sync python -c "import breakdown"
uv run --no-sync python -m breakdown --check
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy breakdown
uv run --no-sync python evals/run.py --offline
```

Add focused tests for package layering, single-entry-point enforcement, AST-only discovery (including a module that raises if imported), misplaced docstrings, duplicate YAML keys, invalid definition fields/types, agent-id/folder mismatch, unresolved or invalid contract references, no import-time agent construction, and preservation of permission/approval boundaries.

These commands have **not** been run for this documentation-only migration slice. No runtime behavior or completed source migration is claimed.

## Consolidation stop rule

Do not delete the current package, old role modules, or old SKILL files merely because the destination folders have been created. Move, repoint every consumer, run the relevant tests, and then delete the old owner in the same reviewed consolidation slice. If a source owner or dependency edge is uncertain, leave it untouched and record the exact evidence needed.
