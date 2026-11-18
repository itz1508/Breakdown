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

### Gap review round 17 (post-Phase 1) — found and fixed

- G1 (high, fixed): role-authored processing plans were missing from role outputs.
  Definition declares creates_processing_plan.authored_by auditor/auditor/planner, but
  the three output models carried no plan field. Fix: added
  research_execution_processing_plan / implementation_planning_processing_plan /
  build_execution_processing_plan to the three outputs, mappers emit them, and a
  contract-layer semantic validator now proves each plan's expected_output_keys are a
  subset of the destination stage's declared produces.
- G2 (high, fixed): no produces-coverage invariant existed. Fix: research_todo added to
  ResearchExecutionOutput (researcher work-product); RUNTIME_OWNED_KEYS registry in
  contracts.py names the deterministic owner of every runtime-produced key;
  test_produces_coverage_invariant + test_mapper_key_declarations_match_behavior pin it;
  `--check` now reports "produces coverage: full" and exits 1 on any uncovered key.
  The drift guard immediately caught one real omission (proposal mapper) during the fix.
- G3 (med, fixed): tests/test_engine.py added — 13 rows: load errors (missing/invalid/
  non-mapping/unknown key), cycle rejection, unproduced requires, non-contiguous orders,
  5 loop-back violation rows, resolve_next matrix, CLI success + failure exit codes.
- G4 (med, fixed): tests/test_bootstrap.py added — aligned Application, 4-role registry,
  valid/invalid binding files, RoleToolkit allowlist denial rows.
- G5 (med, fixed): bootstrap now runs validate_binding on every loaded binding
  (fail fast; stale version raises BindingNotValid before any role is constructed).
- G6 (low, fixed): dead conftest.make_task_payload removed.
- G7 (low, tracked): decision activator emits {"decision": …} placeholder; durable
  output_by_action records belong to Phase 2 approvals (P2-T5).
- G8 (low, fixed): AGENTS.md rule 5 scope clarified (workflow-execution agents vs
  repository maintenance).

Gap-fix commit: `a177840` (gate re-verified at that revision: 89 tests, ruff clean,
mypy strict clean, --check 8 aligned + coverage full, evals 11/11).

## Phase 2 Plan (proposed 2026-11-17, pending execution)

Purpose: durable runtime — artifacts, runs, approvals, safety boundary, deterministic
planning ops, full engine lifecycle — so a real request can travel all 8 stages to a
synchronized, evidence-backed completion. Ports carry provenance from
d:\breakdown\system\storage\ (inspect before porting).

| Task | Files | Content | Named check |
|---|---|---|---|
| P2-T0 | breakdown/canonical.py | canonical JSON (sorted keys) + sha256; digest recipes per yaml digests block | known-answer vectors |
| P2-T1 | breakdown/artifact_store.py | CAS under .breakdown/artifacts/, atomic writes, revisions, digest-verified reads | roundtrip + tamper rows |
| P2-T2 | breakdown/events.py | append-only run event log; persistent/ephemeral split via WorkflowEvent.persistence | split rows |
| P2-T3 | breakdown/run_store.py, checkpoint.py | RunState machine, attempts, resume points, definition pinning; source_checkpoint deterministic op | tmp-git-repo vectors |
| P2-T4 | breakdown/safety.py | absorbs tool containment; sandbox lifecycle; independent changed-path detection; sync authorization/reconciliation | unlocks 3 not_run zeros |
| P2-T5 | breakdown/approvals.py | durable decision activator emitting output_by_action keys; binding digests; approval_hash; timeouts; request_changes loop counter (max 3, invalidation, on_exhausted) | approve/decline/changes/timeout/loop rows |
| P2-T6 | breakdown/planning_ops.py | freeze_plan + preflight_check implementing the 14 declared checks | valid+not_valid row per check |
| P2-T7 | engine.py extension | start_run (pin+checkpoint), contract-driven stage loop, persistence, plan activation rules, budget enforcement (500k/200, reserve 50k, on_exceeded→completion failed budget_exhausted), recovery (max 2), cancellation, completion accepts matrix | e2e success/cancel/loop/budget/recovery |
| P2-T8 | breakdown/reports.py | MD projections referencing JSON sources; record_completion op | source-ref rows |
| P2-T9 | bootstrap + __main__ | stores under .breakdown/; backends only from validated bindings; CLI run/decide/resume/status | CLI smoke rows |
| P2-T10 | evals expansion | score the 3 builder zeros via safety boundary; approval-staleness cases | all 8 zeros scored offline |

Phase 2 gate: all existing tests stay green; new unit+e2e green; ruff/mypy clean;
--check with coverage; evals score all 8 blocking zeros; one scripted e2e run reaches
completion/success with approved paths synchronized only.

🟧 ASSUMPTION: Phase 2 stays offline (fake backends); live SDK evaluation remains a
separate binding milestone.

