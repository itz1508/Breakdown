# Breakdown Package Consolidation Plan

**Date:** 2026-11-25  
**Repository:** `itz1508/Breakdown`  
**Baseline branch:** `main`  
**Baseline commit:** `71218fe820208ff3b5e6118ea5c017568f7a5a73`  
**Working branch:** `migration/latest-four-agent-layout`  
**Status:** source inventory and migration plan; Python source has not yet been moved in this first slice.

## Objective

Consolidate the current flat `breakdown/` package and top-level `agents/skills/` documentation into the four-agent package layout in [current-architecture-workflow.md](current-architecture-workflow.md). During pure package relocation, preserve current executable behavior, serialized artifacts, persistence, and test assertions. The latest target workflow is a material replacement of the current eight-stage workflow, not a behavior-preserving file move; its schema, state, gates, and runtime behavior must be migrated as a separate, explicit workstream. Delete legacy paths only after their contents and references have been migrated and the relevant checks have run.

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
| `breakdown/models.py` | `breakdown/shared/{base,models,config}.py` and `breakdown/shared/queue/` | Split strict base, cross-agent Pydantic models, and settings/configuration. Replace the current `BuildTask`/implementation-plan work representation with the agreed `TaskTodo` representation as an explicit schema/behavior change; do not turn it into a deferred scheduler. Preserve serialized fields only where they remain part of the approved target. |
| `breakdown/contracts.py` | `breakdown/shared/` and `breakdown/system/runtime/` | Split shared protocols/types from runtime activation, registry generation, mapping, and workflow-dependent validation. Do not create a separate `contracts/` directory. |
| `breakdown/roles/__init__.py` | `breakdown/agents/loop.py` and `breakdown/system/tools/` | Split pure model-loop helpers (`generate_structured`, structured-output validation, prompt rendering) into `agents/loop.py`. Move `RoleToolkit`, tool grant checks, and dispatch wrappers to the System tools boundary; agents receive only an authorized injected capability. Do not move authorization into agent code. |
| `breakdown/roles/auditor.py` | `breakdown/agents/auditor/agent.py` | Consolidate Auditor definition and implementation. |
| `breakdown/roles/coder.py` | `breakdown/agents/auditor/coder.py` | Preserve as an Auditor-owned, read-only capability, not an independently dispatched agent. |
| `breakdown/roles/researcher.py` | `breakdown/agents/researcher/agent.py` | Consolidate Researcher definition and implementation. |
| `breakdown/roles/planner.py` | `breakdown/agents/planner/agent.py` | Consolidate Planner definition and implementation. |
| `breakdown/roles/builder.py` | `breakdown/agents/builder/agent.py` | Consolidate Builder definition and implementation. |
| `agents/skills/{auditor,researcher,planner,builder}/SKILL.md` | Matching agent's YAML module docstring | Merge canonical instructions once. Remove manually maintained duplicates after AST discovery and all consumers use the docstring. |
| `agents/skills/coder/SKILL.md` | Auditor's YAML definition / Auditor-owned Coder capability | Coder is not a dispatched agent. Reconcile its read-only instructions into the Auditor-owned capability definition; do not create a fifth agent folder or a separately maintained prompt source. |
| `breakdown/engine.py`, `approvals.py`, `planning_ops.py`, `completion.py`, `verification.py`, `bootstrap.py`, `bot.py`, `reports.py` | `breakdown/system/runtime/` | Move runtime-owned behavior; inject agent instances from `__main__.py`; Runtime must not import agent modules. |
| `breakdown/artifact_store.py`, `events.py`, `run_store.py`, `checkpoint.py`, `canonical.py` | `breakdown/system/storage/` | Move existing persistence/digest owners without adding a second store or changing durable formats. |
| `breakdown/tools.py`, `semantic_search.py` | `breakdown/system/tools/` | Move canonical tool definitions and handlers, preserving role allowlists and dispatch checks. |
| `breakdown/safety.py` | `breakdown/system/safety.py` | Preserve path containment, sandbox integrity, changed-path detection, and synchronization authorization. |
| `breakdown/memory.py` | `breakdown/system/memory.py` (proposed path) | Keep one persistence owner. The file's target semantics remain open: run records versus model context must be decided; do not duplicate RunStore or silently redefine memory. |
| `breakdown/bindings.py`, `live_backend.py`, `demo.py` | `breakdown/system/runtime/` (exact sub-ownership to verify) | Preserve provider binding validation and live/offline backend selection; do not invent a provider abstraction. |
| `breakdown.yaml` | Existing repository-level path, rewritten for the target workflow | Current eight-stage definition still owns executable behavior and references legacy `agents/skills/*.md` paths. Do not change these references until the four YAML agent definitions and new runtime contracts exist. The target specification/research/audit/planning/package-confirmation/build/independent-validation flow requires deliberate workflow-schema migration, not a blind path substitution. |
| Root `tests/` | Agent-local, `shared/tests/`, `system/tests/`, and `breakdown/tests/` | Move tests beside their owners. Keep only layering, cross-agent contract, and workflow-level tests at package root. Never weaken or delete assertions to accommodate a move. |
| `evals/`, `scripts/`, `pyproject.toml`, `bindings.example.json` | Existing repository-level locations, updated in place | Update imports, package discovery, tool/test configuration, bindings, and verified commands after target modules exist. |

The target tree does not prescribe a new `host/` or `contracts/` directory. `agents/prompt.py` is a target helper with no one-to-one current source file; add it only for demonstrated prompt formatting/assembly and never as a parallel instruction source. Runtime remains the workflow authority in this revision. `shared/queue/TaskTodo` is a work representation only, not a scheduler. Do not create additional schedulers, queues with deferred execution semantics, agents, stores, or entry points.


## Gap found: workflow and work-item semantics are not a directory rename

The source currently executes the eight-stage `breakdown.yaml` workflow and uses current `ImplementationPlan`/`BuildTask` records. The latest target has a different sequence: accepted specification review, accepted-item research, Auditor evidence comparison, Planner-authored TaskTodo, exact package confirmation, Builder sandbox/export/exit, independent validation, and retention. A module move cannot make these semantics equivalent. Keep the existing runtime executable until the target state model, transitions, gates, and persistence behavior are implemented and verified. Treat the workflow conversion and BuildTask-to-TaskTodo conversion as explicit schema/behavior changes, not compatibility-preserving renames.

The current config still points to `agents/skills/auditor/SKILL.md`, `researcher/SKILL.md`, `coder/SKILL.md`, `planner/SKILL.md`, and `builder/SKILL.md`. These are valid dependencies of the current implementation. Their removal is gated on new YAML docstring discovery being available to Runtime and every config/test consumer being repointed.

## Test relocation inventory

The baseline root test tree includes `test_roles.py`, `test_contracts.py`, `test_workflow.py`, `test_definition_consistency.py`, `test_approvals.py`, `test_artifact_store.py`, `test_bindings.py`, `test_bootstrap.py`, `test_bot.py`, `test_canonical.py`, `test_checkpoint.py`, `test_cli_live.py`, `test_cli_runtime.py`, `test_completion_reports.py`, `test_engine.py`, `test_engine_budget_recovery.py`, `test_engine_lifecycle.py`, `test_evals_scoreboard.py`, `test_events.py`, `test_lifecycle.py`, `test_live_backend.py`, `test_live_retry.py`, `test_memory.py`, `test_planning_ops.py`, `test_run_store.py`, `test_safety.py`, `test_stage_usage.py`, `test_tools.py`, and `test_verification.py`, plus `conftest.py`.

Do not infer their exact new owners from filenames alone. Inspect assertions and imported production owners in each test. Split `test_roles.py` by intact agent-specific test functions; move Runtime/Storage/tool/safety tests with their production owner; retain workflow and layer-boundary tests in `breakdown/tests/`. If one file tests multiple owners, partition only by moving complete test cases without altering their contents. Record the source-to-destination test map before the move.

## Migration phases

### Phase 0 — Baseline and target contract

- Pin the source commit and record current paths, active imports, settings, entry points, tests, and workflow definition.
- Publish the target tree, agent ownership rules, static YAML-definition rules, and migration map.
- Keep `main` unchanged while the migration is reviewed.

### Phase 1 — Shared contracts, configuration, and TaskTodo

- Split `StrictModel`, cross-agent Pydantic models, and settings into `shared/base.py`, `shared/models.py`, and `shared/config.py`.
- Add the shared `TaskTodo` representation under `shared/queue/`; map existing `BuildTask` and plan records to it deliberately, preserving required identity, provenance, and confirmation digest semantics without retaining scheduling/wave abstractions.
- Separate shared protocol/types from runtime contract activation without creating an extra `contracts/` directory.
- Move and update focused shared-contract tests; verify AST layering and import direction.

### Phase 2 — Agent consolidation

- Move the four agent implementations into their owning folders; move Coder under Auditor.
- Merge each agent's current SKILL guidance and implementation prompt into one canonical YAML module docstring. Coder's read-only instruction content is owned by Auditor's definition/capability, not a fifth agent definition. Agent prompt helpers may format the metadata but must not duplicate its instruction text.
- Add import-free AST discovery, first-statement/docstring checks, duplicate-YAML-key rejection, strict Pydantic validation, folder/id matching, and static shared-contract reference validation.
- Put agent-specific tests in each agent folder. Remove old skill/role paths only after imports and tests point to the new owners.

### Phase 3 — Runtime, Storage, tools, safety, and memory

- Move runtime orchestration and approval/plan/completion behavior under `system/runtime/`.
- Move existing durable stores and digest/checkpoint owners under `system/storage/`.
- Move canonical tools under `system/tools/`; retain the existing permission allowlists.
- Move safety and memory to their designated `system/` owners.
- Keep `system/` independent of agent imports; inject the constructed agent set from the composition root.

### Phase 4 — Target workflow and state migration

- Map the current eight workflow stages, transitions, artifact keys, approval records, and persisted state to the latest target flow. Record every source mapping and every removed/changed behavior.
- Implement the accepted-specification revision/Accept & Check loop, accepted research items, Auditor evidence comparison, Planner TaskTodo, exact package confirmation bound to the source checkpoint, Builder sandbox/export/exit, independent validation, and completion/retention.
- Replace the current `breakdown.yaml` and its role-guidance paths only after the new Pydantic models, Runtime transitions, and agent definitions are wired. Preserve old persisted-run compatibility only where actual persisted data and an explicit migration policy require it.
- Keep unresolved policy choices (Builder model invocation/stop behavior, confirmation after corrected to-do, loop caps, handoff fields, and memory semantics) out of code defaults; mark them open and block only the behavior they materially control.

### Phase 5 — Composition root and repository consumers

- Make `breakdown/__main__.py` the sole composition root that constructs the four agents and passes them to Runtime.
- Update all imports in package code, tests, evals, scripts, and documentation.
- Update `breakdown.yaml` role-guidance references so no executable configuration points at retired files.
- Update `pyproject.toml` package discovery, test paths, lint exclusions, and strict type-check paths from actual package layout.

### Phase 6 — Test relocation and consolidation checks

- Move tests without editing, deleting, reordering, or combining test cases/assertions. Split combined role tests only by moving intact test functions into the owning agent folders.
- Keep only layering, cross-agent contract, and workflow-level tests in `breakdown/tests/`; keep each agent's tests in its own folder, shared-model tests in `shared/tests/`, and Runtime/Storage/tool/safety tests in `system/tests/`. The illustrative tree uses `tests/`, but do not finalize `tests/` versus `test/` until the open naming decision is resolved.
- Retain `evals/` and `scripts/` at repository root unless a verified owner change requires moving them.
- Update `pyproject.toml` so test discovery, package inclusion, linting, formatting, and strict type-checking cover all nested packages.

### Phase 7 — Legacy removal and consolidation gate

Remove a legacy file or directory only after all of the following are true:

1. Its behavior and required instructions have an identified target owner.
2. All runtime, tests, evals, scripts, config, docs, and import references use the target owner.
3. No remaining code path imports the legacy module or reads its old skill path.
4. Focused owner tests and cross-boundary tests pass.
5. Full offline verification passes and the resulting diff shows no lost behavior or unexplained test reduction.

Then remove the retired `breakdown/roles/`, the old top-level `agents/skills/` tree, migrated flat modules, and root tests that have been relocated. Retain root-level `evals/`, `scripts/`, and repository manifests unless source evidence justifies another owner. Before deleting old paths, also verify that target protection rules cover the new nested `breakdown/agents/`, `breakdown/shared/`, and `breakdown/system/` application paths; current protection rules were written for the old top-level layout.

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
