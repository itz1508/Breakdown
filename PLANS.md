# OneShot Breakdown — Clean-Baseline ExecPlan (PLANS.md)

Living document. Progress, Surprises & Discoveries, Decision Log, and
Outcomes & Retrospective are kept current as work proceeds. Maintenance
follows the Codex PLANS.md discipline: every stopping point documented,
exact commands with expected results, acceptance phrased as behavior.

## Purpose / Big Picture

After this work, a person can point Breakdown at a repository and enter a
plain-language request. Breakdown executes eight explicit stages:

research_proposal → research_approval → research_execution → findings_review
→ implementation_planning → plan_approval → build_execution → completion

with two real user approvals, one authoritative ImplementationPlan,
sandbox-only builds, independent changed-path detection, and
Runtime-authorized synchronization of approved paths only.

Phases:
- Phase 1 (current): five roles + contracts + canonical tools + offline evals.
- Phase 2: storage/safety/approvals/full engine (`system/storage` family ports).
- Phase 3: `mcp`/plugin deployment separation, only on evidence.

## Progress

- [x] (2026-11-17) M0 repository assessment of d:\breakdown (owners: ArtifactStore/CheckpointStore/EventStore/ReceiptStore exist; WorkflowEngine/ContractRegistry/RunStore absent; no model SDK declared; no CI/pre-commit; no persisted 8-stage runs)
- [x] (2026-11-17) Task 0: D:\Breakdown-tmp created; git initialized; breakdown.yaml (def-1 seed) copied
- [x] (2026-11-17) Task 1 (part 1): manifests written (pyproject.toml, .gitignore, .python-version, .env.example, AGENTS.md, breakdown/__init__.py, PLANS.md)
- [x] (2026-11-17) Task 1: manifests + uv.lock (22 packages) + uv sync --locked + import smoke (`import breakdown` → 0.1.0; pydantic 2.14.3, pyyaml 6.0.3, Python 3.11.15)
- [x] (2026-11-17) Task 2 (part 1): tests/test_workflow.py written; breakdown.yaml seeded at Task 0
- [x] (2026-11-17) Task 2: breakdown.yaml seeded (def-1, verified verbatim) + tests/test_workflow.py — 13/13 passed
- [x] (2026-11-17) Task 3: agents/skills ×5 SKILL.md (v7-operation vocabulary, good/bad cases)
- [x] (2026-11-17) Task 4: breakdown/models.py (791 lines) + tests/conftest.py; live parse of breakdown.yaml through WorkflowDefinition verified
- [x] (2026-11-17) Task 5: breakdown/tools.py (capability_inspect, source_search, source_read + registry + dispatch)
- [x] (2026-11-17) Task 6: breakdown/contracts.py (StageContract, 3 activators, output mappers, registry generator, alignment)
- [x] (2026-11-17) Task 7: breakdown/engine.py (load_workflow, forward DAG via graphlib, bounded loop-backs, resolve_next)
- [x] (2026-11-17) Task 8: breakdown/roles/ ×5 (auditor, researcher, coder, planner, builder)
- [x] (2026-11-17) Task 9 (part): bindings.py, bootstrap.py, __main__.py, evals/ — offline evals 11/11 passed; 5 scored blocking zeros at 0 violations; 3 zeros not_run pending Phase 2 safety boundary
- [x] (2026-11-17) `python -m breakdown --check`: 8 stages ↔ 8 contracts aligned, 0 mismatches
- [x] (2026-11-17) Task 9 (rest): test_contracts/test_tools/test_roles/test_bindings written; full gate green
- [x] (2026-11-17) Phase 1 gate PASSED: pytest 64 passed · ruff check clean · ruff format 30 files clean · mypy strict 14 files 0 issues · `python -m breakdown --check` 8↔8 aligned · evals 11/11, 5 scored zeros at 0 violations, 3 zeros not_run (Phase 2 safety boundary)
- [x] (2026-11-17) First commit after gate: `ba9d0e1` on `main` — 41 files, working tree clean

## Surprises & Discoveries

- Observation: the def-1 seed file was renamed by the browser to `breakdown (1).yaml` between sessions; original path vanished. Evidence: Downloads search found only `breakdown (1).yaml` (20,786 bytes); copied as seed. Content verified verbatim as the def-1 clean baseline (8 stages, vocabularies, schema_validation, dependency_validation).
- Observation: git identity in this environment is placeholder (`Test <test@example.com>`). Evidence: `git config --get user.name/email`. Consequence: fine for local history; must be corrected before any push/publication.
- Observation: def-1 seed declares `cost_budget.on_exceeded: route completion / terminal_outcome failed`, while the workspace v7 file declared `pause_and_request_user_decision`. Evidence: both files read verbatim. Resolution: seed (def-1) governs this build; contradiction recorded, not silently discarded.
- Observation: def-1 seed adds a `synchronization` ownership block to build_execution (`execution_owner: execution_service`) and explicit `dependency_validation` edge lists. Evidence: seed lines 578-588, 182-242. Engine/tests will honor them.
- Observation: seed stage 1 produces `candidate_source_responsibilities` (v7 worktree used `proposed_file_responsibilities`). Evidence: seed line 258. Models/tests use the seed's key.

## Decision Log

- Decision: Build at `D:\Breakdown-tmp` (drive root, outside the workspace repo). Rationale: user directive; zero contact with existing d:\breakdown tree; no preservation required. Date/Author: 2026-11-17 / user.
- Decision: `git init` at the target; first commit after Phase 1 gate. Rationale: independent location (no nested-repo conflict); commit pattern approved with the plan. Date/Author: 2026-11-17 / user (plan acceptance "correct").
- Decision: `definition_version: 1` clean baseline; no compatibility aliases. Rationale: ExecPlan rule — no persisted production records exist (M0: .oneshot-state holds harness-era tables only). Date/Author: 2026-11-17 / ExecPlan.
- Decision: breakdown.yaml seeded from the user's def-1 reference file. Rationale: D2 default accepted; file verified verbatim (8 canonical stages, 3 processing plans, validation catalogs). Date/Author: 2026-11-17 / agent (verified).
- Decision: Phase 1 runtime deps = pydantic, pydantic-settings, pyyaml only; no model SDK until an evaluation-backed binding exists. Rationale: ExecPlan non-goals + M0 reuse assessment. Date/Author: 2026-11-17 / plan D6 default.
- Decision: Python >=3.11. Rationale: installed interpreter 3.11.15; D3 default not vetoed. Date/Author: 2026-11-17.
- Decision: backend protocols live in contracts.py; roles import only models/contracts/tools; fakes in tests. Rationale: H4/H14 gap fixes; role-independence boundary rule. Date/Author: 2026-11-17 / gap round 16.
- Decision: old harness-era tree at d:\breakdown remains untouched; spec_search and legacy modules are retired from this product by omission, not migration. Rationale: clean baseline; external scaffold is reference only. Date/Author: 2026-11-17.

## Context and Orientation

- `D:\Breakdown-tmp\breakdown.yaml` — the single declarative workflow authority (def-1, 8 stages).
- `breakdown/` — product package. Phase 1 modules: `models.py`, `contracts.py`, `engine.py`, `tools.py`, `bindings.py`, `bootstrap.py`, `roles/`.
- `agents/skills/<role>/SKILL.md` — optional guidance only; never executable authority.
- `evals/` — offline role evaluation harness (fake backends in Phase 1).
- Reference repository (patterns only, no imports): `d:\breakdown\system\storage\` (ArtifactStore CAS + canonical serialization), `d:\breakdown\agents\shared\providers\base.py` (request/result shapes).

## Plan of Work

Ordered cohesive BuildTasks T0–T9 as approved in the Phase 1 plan
(gap round 16 corrections applied): one task = one cohesive change,
each with target paths, expected result, and named check. Task 0 done.
Current: finish Task 1 (dependency install), then T2–T9 in order,
each verified before the next.

## Validation and Acceptance

Run from `D:\Breakdown-tmp`:

    uv lock; uv sync --locked
    uv run --no-sync python -m compileall breakdown tests evals
    uv run --no-sync python -c "import breakdown"
    uv run --no-sync python -m breakdown --check
    uv run --no-sync pytest -q
    uv run --no-sync ruff check .
    uv run --no-sync ruff format --check .
    uv run --no-sync mypy breakdown
    uv run --no-sync python evals/run.py --offline

Phase 1 is accepted when all commands exit 0, `--check` reports
8 stages ↔ 8 contracts aligned, and the offline evals score the eight
blocking zeros. A check is meaningful only if breaking the protected
behavior makes its named test fail.

## Idempotence and Recovery

All Phase 1 steps are repeatable: manifests are declarative, `uv sync`
is idempotent, tests use tmp fixtures only, no step touches the network
or the reference repository. If a task fails, previous passing tasks
remain intact; fix forward, never edit tests to force success.

## Interfaces and Dependencies (Phase 1 targets)

- `breakdown.models`: StrictModel (extra=forbid), ExecutionResult, CriterionResult,
  FindingStatus, CapabilityCoverage, ContractKind, RunState, Settings,
  WorkflowDefinition/StageDefinition, role I/O records, ProcessingPlan,
  ArtifactRef, SourceCheckpoint, UserDecision, approval records, BackendBinding.
- `breakdown.contracts`: StageContract, ContractRegistry (generator deriving
  requires/produces from the definition), RoleBackend/CodingBackend protocols,
  role/decision/deterministic activators.
- `breakdown.engine`: load_workflow, forward-edge (graphlib) and loop-back
  validation, resolve_next.
- `breakdown.tools`: capability_inspect, source_search, source_read.
- `breakdown.roles`: Auditor (2 ops + coder sub-role), Researcher, Coder,
  Planner, Builder — async typed operations, injected backends/tools.

## Outcomes & Retrospective

### Phase 1 delivered (2026-11-17)

- `D:\Breakdown-tmp` initialized (git), def-1 `breakdown.yaml` seeded and verified verbatim.
- Package `breakdown/` (14 modules, mypy-strict clean): models (929 lines, 60+ typed
  contracts, OPERATION_IO), contracts (generator registry, 3 activators, explicit output
  mappers), engine (definition loading, graphlib forward DAG, bounded loop-backs,
  resolve_next), tools (3 canonical tools + containment), bindings (invalidation rules),
  bootstrap, `__main__ --check`, roles ×5.
- `agents/skills/` ×5 SKILL.md (data-only; structure pinned by test).
- `evals/` offline harness: 11/11 cases; blocking zeros scored where Phase 1 can enforce
  them; builder-side zeros honestly `not_run` pending the Phase 2 safety boundary.
- Tests: 64 passing (workflow definition 13, contracts 13, tools 14, roles 15, bindings 9).
- Environment surprise handled: user Temp denies pytest basetemp (WinError 5) →
  project-local gitignored `--basetemp=.pytest-tmp` (mirrors the reference repo workaround).
- Lesson: PowerShell here-string appends via pasted terminal input can land late; verify
  file state by line count AND content boundaries before appending more (one duplicate
  block caught by ruff F811 and excised).
