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
- Decision (D11–D22, approved with the Phase 2 plan 2026-11-18): rfc8785>=0.1.4 runtime dep for JCS canonicalization; SQLite for artifact/event/run stores (corrects the earlier JSONL sketch after reference inspection); state in `<target_repo>/.breakdown/`; non-git checkpoint fallback supported; sandbox = copy of checkpoint-listed files (VCS excluded); source_checkpoint_hash over the seed's full identity tuple; definition_digest = sha256(canonical_json(parsed definition)); loop exhaustion → completion failed (reason loop_exhausted); single-writer lockfile guard; engine task split T7a/T7b; Phase 2 stays offline; timeouts enforced on access (no daemon).
- Decision (Agent middleware, 2026-11-24): adopt a shared Input → Wrap → Output middleware pipeline around the Agent model-invocation and tool-execution interception points. Agent instances may register middleware; each Agent continues to define its own domain request/output contract in its own `agent.py`. Shared middleware stage contexts, results, tokens, and dispatch belong in `breakdown/agent/middleware.py`, not a new Agent `contracts.py` or `shared/base.py`. Runtime retains workflow transitions, user approvals, execution budgets, and immutable tool authorization. This records the design direction only; implementation requires a separate source-rechecked plan and approval.

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
| P2-T2 | breakdown/events.py | SQLite append-only run event log (ported pattern; earlier JSONL sketch corrected after reference inspection); persistent/ephemeral split via WorkflowEvent.persistence | split rows |
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

## Phase 2 Progress

- [x] (2026-11-18) P2-T0 canonical.py — RFC 8785/JCS port (rfc8785 0.1.4) + five digest
  recipes (definition, artifact, source_checkpoint, frozen_plan, approval); 12 tests incl.
  JCS known-answer vectors. Provenance: d:\breakdown\system\storage\canonical_serialization.py
- [x] (2026-11-18) P2-T1 artifact_store.py — SQLite CAS, immutable revisions, idempotent
  same-content writes, digest-verified reads, schema-validated get_model; 8 tests.
  Provenance: d:\breakdown\system\storage\artifact_store.py
- [x] (2026-11-18) P2-T2 events.py — SQLite append-only log over WorkflowEvent; ephemeral
  events rejected from the durable log; canonical JSON lines with digest verification on
  load; cursor pagination; 6 tests. Provenance: system\storage\event_store.py
- [x] (2026-11-18) P2-T3 run_store.py + checkpoint.py + RunRecord model — CAS run state
  with competing-writer rejection, definition pin immutable after run start, tamper
  detection; checkpoint capture for git (origin/HEAD/tracked/untracked) and non-git
  fallback; freshness comparison; 15 tests incl. tmp git repos.
  Provenance: system\storage\checkpoint_store.py (CAS pattern)
- [x] (2026-11-18) Gate A PASSED: pytest 130 passed · ruff check clean · ruff format clean ·
  mypy strict 19 files 0 issues · --check 8 aligned + produces coverage full · evals 11/11
  (5 scored zeros 0 violations; 3 builder zeros not_run until P2-T4)
- [x] (2026-11-18) P2-T4 safety.py — containment authority moved from tools.py (tools now
  delegate); SafetyBoundary: checkpoint-listed sandbox, independent hash-diff changed-path
  detection, authorization per yaml synchronization.requires, atomic reconciled copy-back,
  protected-path refusal; 17 tests. The three builder blocking zeros are now enforceable.
- [x] (2026-11-18) P2-T5 approvals.py — durable decision activator (closes G7): pending
  decisions with binding refs/digests captured at pause, ApprovalBindingStale enforcement,
  ResearchApprovalRecord/PlanApprovalRecord with full decision_binding fields, approval_hash
  per canonical recipe, timeout-on-access → cancelled, request_changes loop counter with
  definition-derived max_loops/invalidation, loop exhaustion → failed (D18/D24); 14 tests.
  Models added: PendingDecision, StoredValue, RunRecord.produced_artifacts (D23).
- [x] (2026-11-18) P2-T6 planning_ops.py — freeze_plan + run_preflight implementing all 14
  declared checks as pure deterministic functions + PLANNING_OPERATIONS adapters for the
  deterministic-op registry; 14 tests.
- [x] (2026-11-18) Gate B PASSED: pytest 177 passed (0 F/0 E) · ruff check clean ·
  ruff format 48 files clean · mypy strict 22 files 0 issues · --check 8 aligned +
  produces coverage full · evals 11/11 (zeros unchanged until P2-T10 wiring)
- [x] (2026-11-18) P2-T7a engine happy path — WorkflowEngine on the stores: start_run
  (definition pin via canonical digest + checkpoint capture), contract-driven advance loop
  with per-stage input assemblers, artifact persistence (StoredValue envelope for non-model
  values), runtime post-steps (freeze+preflight after planning; sandbox→detect→authorize→
  synchronize→reconcile after build), decision pauses via ApprovalManager, record_decision
  bridge, cancel, completion with accepts-matrix validation; per-run role construction
  (D25); cross-instance resume proven. 6 e2e tests incl. full scripted run reaching
  completion/success with real file sync into the target repo.
  Cycle-1 gap pass found & fixed: (1) forward arrival at completion defaulted to failed —
  success path now derives outcome success; (2) completion accepts matrix requires
  retained_evidence on cancelled/failed routes — approvals + engine terminal routes now
  persist it; (3) STAGE_ENTERED was duplicated for stage 1 and missing for decision stages —
  entry events now emitted exactly once per stage entry (7 per full run, pinned by test).
  Validation points hooked: 7/8 (budget point lands with T7b); observability events: 8/9
  (cost_threshold_approached lands with T7b).
- [x] (2026-11-18) P2-T7b budget/recovery/timeout/uncertainty routing — engine enforces
  cost_budget from the pinned definition: per-stage default_max_tokens, workflow max_tokens /
  max_tool_calls, completion_reserve (checked before every role stage and after every
  activation), on_exceeded → completion/failed reason budget_exhausted with
  budget_exhausted_record + failure_record + retained_evidence preserved; 80% threshold
  emits cost_threshold_approached (9/9 observability events, 8/8 validation points).
  stage.on_failure runtime_recovery retries in place up to max_recovery_attempts (durable
  per-attempt commits, resume_point recorded); build/completion route straight to
  completion/failed. timeout_seconds wraps activation via asyncio.wait_for
  (error_type timeout). D27 uncertainty routing: build task uncertainty takes the loopback
  edge (sandbox torn down, synchronization prohibited, replanning + NEW plan approval
  required); non-build uncertainty routes completion/failed without recovery.
  Cycle-2 fixes: (1) approved_plan_revision stored the artifact-store revision instead of
  the ImplementationPlan model revision — builder revision check broke on replanning; now
  model revision. (2) roles surface backend usage via generate_structured helper
  (role.last_usage) so the engine can accumulate budget.
  🟨 PROPOSAL (guardrail, later adopted as D29): build→plan loopback bounded at 3 build
  attempts (_MAX_BUILD_ATTEMPTS) — yaml declared the edge but no cap; unbounded looping
  violates recovery discipline. (3) known limitation (CLOSED in the polish cycle after
  D29): coding-backend (builder) usage was not counted toward the budget —
  CodingBackendResult now carries usage and the builder accumulates it.
  10 new test rows (per-stage cap, reserve + threshold event, workflow max tokens,
  tool-call cap, budget boundaries, recovery retry/exhaustion, timeout exhaustion,
  loopback-then-success, build not_valid).
- [x] (2026-11-18) P2-T8 reports + completion op — `completion.py`: record_completion as a
  first-class deterministic operation (COMPLETION_OPERATIONS registry mirroring
  PLANNING_OPERATIONS): data-driven accepts-matrix validation over the yaml completion
  block (all four outcomes covered by parametrized rows), CompletionRecord assembly with
  terminal_state mapping, retained_evidence now wired into the record (failed/cancelled
  routes cite the evidence bundle ref). Engine _complete_run delegates to it. `reports.py`:
  deterministic Markdown projections citing every artifact as key@revision + CAS digest
  (verifiable against the stores; no payloads, no wall-clock). 13 test rows incl. engine
  integration for success + failed completion. Cycle-3 fix: collections.abc.AbstractSet
  does not exist on CPython 3.11 — use collections.abc.Set.
- [x] (2026-11-18) P2-T9 bootstrap.build_runtime + CLI — `build_runtime()` wires stores
  under `<target>/.breakdown/` (D12), LockfileGuard (atomic O_EXCL pid lock; foreign lock
  aborts, --force-unlock takes over known-stale locks; release only deletes own lock — D18),
  ApprovalManager, per-run role factory, and the engine; bindings validated unless
  --offline-demo (D26). `demo.py`: scripted offline backends (validator-passing outputs;
  demo coding backend creates DEMO_CHANGE.md in the sandbox). CLI: run / resume / decide /
  cancel / status subcommands + --check retained; status is read-only (no lock, no
  backends) and prints the reports.py Markdown; demo resume re-reads the stored
  initial_request for backend scripting. Cycle-4 fix: demo decision_trace observation is a
  'true'/'false'/'unknown' literal. 10 new tests incl. subprocess e2e: separate CLI
  processes drive run→decide→resume→decide→resume to success with DEMO_CHANGE.md
  synchronized into the target, plus cancel, lock-contention, and error paths.
- [x] (2026-11-18) P2-T10 evals expansion (Gate C) — all 8 blocking zeros now scored:
  new `harness: safety` cases run the Builder against scripted side-effect coding
  backends (approved write, unexpected sandbox path, rogue direct authoritative write)
  inside a real sandbox and score detection + synchronization authorization through
  the real SafetyBoundary: builder_unexpected_paths, builder_authoritative_repo_writes,
  builder_unauthorized_synchronization (stale-approval bindings_current=false and
  invalid task results) — each blocked as required, plus a positive control proving an
  authorized sync lands in the target. PHASE1_NOT_RUN retired: the scoreboard now
  requires every zero to be exercised (NOT_SCORED fails the run). 16/16 eval cases,
  8/8 zeros at 0 violations. README.md created (quickstart incl. offline demo CLI
  flow); evals/README.md updated. 3 new scoreboard-semantics tests.
- [x] (2026-11-18) Final cycle — comprehensive gap review + closure:
  **yaml consumption audit** (section-by-section): definition block enforced by
  run-store pinning (no mutation path after start); vocabularies, observability
  persistent_events, ownership, build authorization_checks, synchronization.requires,
  digests.algorithm, cost_budget.on_exceeded, and approval_boundary loopback target
  are now PINNED by `validate_definition_consistency` (runs in --check and both
  bootstrap paths) against their runtime implementations (enums, EventType,
  safety.AUTHORIZATION_CHECKS / SYNCHRONIZATION_REQUIRES, canonical.DIGEST_ALGORITHM).
  stop_on_criterion now flows definition → BuildExecutionInput → Builder (was a
  hard-coded redeclaration); cost_budget.on_exceeded terminal_outcome/reason are
  data-driven (were hard-coded). Consumed behaviorally: transitions, output_by_action,
  decision_binding, creates_processing_plan, processing_plan_activation (plan activates
  on decision approve via input assembly), completion_criteria, runtime_steps,
  on_failure, accepts/records/emits, precondition, timeout_seconds, schema_validation
  (8/8 points), dependency_validation, source_rules (researcher provenance validators),
  sub_roles (coder injection into auditor), execution_order sequential (builder loop),
  delegation. Documented-only (declarative policy, executable:false by declaration):
  handoff_rules, role_guidance (consumed by SKILL.md/role briefs), artifact_keys.rules,
  on_budget_exhausted/on_failure preserve lists (runtime preserves the superset of all
  produced artifacts + explicit records). Modeled but unused by def-1: budget_reserve,
  computation_timeout_seconds. G1–G8 all closed (Phase 1 gap fixes + P2-T5 approvals).
  D11–D28 honored as recorded in the cycle entries; the T7b loopback guardrail was
  superseded by D29 (see below). 9 new tests (7 consistency-drift rows, stop-criterion
  flow, on_exceeded policy).
- [x] (2026-11-18) D29 — loopback bound is definition-owned (user-approved plan):
  breakdown.yaml build_execution→implementation_planning edge now declares max_loops: 2
  (edge-traversal semantics, consistent with plan_approval's max_loops consumed by
  approvals; preserves the previously tested behavior of 3 total build attempts).
  _validate_loop_backs now requires a finite max_loops >= 1 on EVERY declared
  dependency_validation.loop_back_edges entry (closes the "unbounded loop declarable"
  enforcement gap the hard-coded constant was masking). Engine _loop_back_for_replanning
  consumes the declared edge via _loop_back_edge(); _MAX_BUILD_ATTEMPTS deleted.
  New tests: declared edge without max_loops rejected at load; loopback exhaustion
  (3 blocked builds) routes completion/failed with error_type uncertainty.
- [x] (2026-11-19) Phase 2 polish cycle — remaining items closed:
  (1) coding-backend usage now budget-counted: CodingBackendResult.usage field,
  Builder accumulates per-task usage into last_usage (engine's generic read picks it
  up; no engine change), demo + test fakes report usage, happy-path test pins the
  exact run total (4 role activations + builder). Closes the last documented
  Phase 2 limitation.
  (2) .env.example gained BREAKDOWN_STATE_ROOT (Settings field added in T9).
  (3) processing_plan_activation blocks pinned by validate_definition_consistency:
  declared plan must be produced by an earlier stage, activated_by runtime, and
  required by the on_approve destination (drift-rejection test added).
  Documented-only facts (no behavior owed in def-1): the `partial` completion
  outcome is unreachable by design — cost_budget.on_exceeded explicitly routes
  terminal_outcome failed and no edge produces partial_build_result; its accepts
  row is declarative future-proofing. ACTIVITY_UPDATED is a reserved ephemeral
  event (persistence-tested, never emitted in Phase 2; exists for a future
  activity feed). Phase 3 (live SDK backends, binding-backed construction, SDK
  capability eval layer) remains decision-gated: provider choice, credential
  conventions, and live-assessment pass criteria are required first.

## Phase 3a — orchestration economics + live OpenAI-compatible backends

Source patterns: Anthropic cookbooks "plan big, execute small" (two-model
team economics, per-thread usage metering, session budget as fan-out
guardrail), "multiagent orchestration" (subagents/threads/advisor), "async
multi-agent orchestration" (hub messaging, spawn/collect/dismiss lifecycles).
CMA's platform API is Anthropic-only; per user direction the patterns are
rebuilt on our own orchestrator (the engine) with live model access through
OpenAI-compatible endpoints (Databricks key or custom API key).

- [x] (2026-11-19) D30 — OpenAI-compatible adapter over CMA SDK: live backends
  speak any /chat/completions endpoint (Databricks Model Serving, custom
  gateway, OpenAI); structured outputs via response_format json_schema with
  prompt-JSON fallback; bounded canonical tool loop (dispatch_tool, allowlist
  enforced twice: advertised schemas + per-call check); usage mapped into
  TokenUsage. New dependency: openai>=1.50,<3 (resolved 2.54.0).
- [x] (2026-11-19) D31 — per-stage cost attribution (per-thread metering
  pattern): RunRecord.stage_usage accumulates per activation (retries and
  loopbacks add to the stage; unreported usage is never invented),
  STAGE_COMPLETED events carry per-activation tokens/tool_calls,
  CostSummary.by_stage projects into the completion record, budget_exhausted
  records snapshot the attribution, reports render a stage-cost table.
- [x] (2026-11-19) D32 — per-role backend seam (two-model team pattern):
  build_runtime(role_backends=...) routes each role to its own backend with
  shared fallback; per-role model tiers via BREAKDOWN_MODEL_<ROLE>. Advisor
  pattern already implemented (auditor's bounded coder sub-role). Hub
  peer-messaging rejected by handoff_rules (roles never invoke roles).
- [x] (2026-11-19) D33 — live path requires validated bindings: CLI --live
  demands a bindings file; coverage check is data-driven from the definition
  (every ROLE stage owner needs a binding whose permitted_operations cover
  its operation). Evidence flow: scripts/live_probe.py -> evals --live ->
  BackendBinding records -> CLI --live. bindings.example.json templates the
  records (live_status valid, openai package version pinned).
- [x] (2026-11-19) D34 — live coding backend is sandbox-confined by
  construction (writes only declared target paths, traversal-checked) AND
  still gated by the safety boundary downstream (detect/authorize/sync).
  Overreach attempts fail the task and write nothing.
- [x] (2026-11-19) D35 — independent verification gates sync authorization:
  when a verifier backend is available, `integration_valid` inside `_post_build`
  is computed from the verifier's per-criterion results, not from the builder's
  self-report. The builder's self-report remains stored as evidence but no longer
  authorizes. If no verifier is configured, the legacy self-report path is used
  unchanged, preserving backward compatibility for eval fakes and existing test
  harnesses.
- [x] (2026-11-19) D36 — memory store + runtime-only writes: lessons are
  written deterministically by the engine at run completion as immutable versions
  in a SQLite CAS under the state root; roles receive read-only memory tools
  (`memory_list`, `memory_read`, `memory_search`); consolidation writes a new
  revision via explicit CLI command; inputs are never modified.
- [x] (2026-11-19) D37 — consolidate-memory = live-only dream equivalent:
  `consolidate-memory --live [--instructions TEXT]` merges accumulated lessons
  into a fresh revision using the live model; without `--live` the command prints
  a refusal and exits nonzero. This reproduces the two reference properties:
  immutable versions as audit trail, and "the input store is never modified."
- [x] (2026-11-19) D38 — live transport retry: transient `429`, `5xx`, and
  connection errors are retried with exponential backoff (honoring
  `Retry-After`) up to three times before the stage's existing recovery takes
  effect. A shared `_with_retry` wrapper covers both role generation and coding
  `apply_task` calls; `retry_base_delay` is injectable for tests.
- [x] (2026-11-19) D39 — Build-Baseline Mapping & Evidence Normalization inventory:
  `docs/researcher-build-inventory.md` establishes the five advanced capabilities
  (semantic search via Databricks AI Search `breakdown_knowledge_index`, autonomous
  tool runner loops, async subagent delegation via Hub message passing, multi-tier
  hosting + Slack bot, and cross-session memory stores) and reallocates authoritative
  `BaselineMap` and `NormalizedEvidence` production to the Researcher role, with
  Auditor `findings_review` serving as the independent verification gate.
- [x] (2026-11-19) D40 — Researcher owns BaselineMap and NormalizedEvidence:
  `ScaffoldingEntry`, `BaselineMap`, and updated `NormalizedEvidence` (carrying
  `source_identity`, `source_location`, `source_version`, `provenance_preserved`) are embedded
  directly inside `ResearchRecord` to preserve 100% definition consistency and contract alignment.
  Canonical `semantic_search` tool implemented with dual-mode execution (Databricks AI Search
  vector index when configured, local lexical/TF fallback offline). Researcher constructs baseline
  module mapping via AST scanning; Auditor's `review_research_findings` independently audits and
  carries forward verified evidence.
- [x] (2026-11-19) D41 — Breakdown Bot independent runtime (`breakdown/bot.py`, CLI `breakdown bot`):
  Refactored from generic Slack bot into native Breakdown Bot architecture learned from Claude Agent
  SDK and Managed Agents cookbooks. Features natural task intent parsing ("go research...", "go plan...",
  "implement..."), typed `BotEvent` streaming (`bot_started`, `intent_resolved`, `stage_started`,
  `stage_completed`, `approval_needed`, `decision_recorded`, `completed`, `failed`), interactive
  decision routing, and cross-session baseline memory inspection.
- [x] (2026-11-19) D42 — Refactor all {slack} to canonical Automations drafts (`breakdown/automations.py`):
  Refactored all Slack integrations from legacy standalone Socket Mode manifests into the canonical
  Automations draft YAML output shape and proto wire format (`prefillWorkflowData` for `open_automation`).
  Enforces the 12 exhaustive trigger oneof keys (`cron`, `git`, `slackTrigger`, `slackReactionAdded`,
  `slackChannelCreated`, `emailReceived`, `microsoftTeamsTrigger`, `microsoftTeamsChannelCreated`, `linear`,
  `webhook`, `pagerduty`, `sentry`), strictly rejecting invented/paraphrased keys. Enforces channel ID
  disciplines (`C…`/`G…` for triggers; `C…`/`G…`/`D…` resolving to owner DM for actions), git `ignoreDraftPrs`,
  and `|` block scalar prompt formatting. Integrated trigger ingestion (`parse_trigger`, `emit_slack_action`,
  `run_trigger_stream`) into `BreakdownBot` and added `automation draft` / `automation validate` CLI commands.
- [x] (2026-11-19) D43 — Runtime lifecycle invariants and scope discipline:
  Supersedes D42 and Slack/Automations draft scaffolding. References are guidance for planning
  and refactor, not source to copy. Enforces:
  1. Async core with one event loop owner per process: `_activate_with_timeout` safely bridges
     running loops via dedicated worker pool without nested `asyncio.run()`.
  2. Backend close lifecycle: `aclose()` and `close()` implemented on `BreakdownBot`, `Runtime`,
     `OpenAICompatibleRoleBackend`, and `OpenAICompatibleCodingBackend`, ensuring underlying
     client connection pools and lockfiles are released on every exit path (complete, cancel, crash).
  3. Explicit `runtime_kind` field on `RunRecord` (`Literal["offline_demo", "live_openai"]`):
     stored explicitly, never inferred from ID prefixes; `engine.advance` enforces runtime affinity
     on resume, rejecting mismatches.
  4. web_fetch: client-side `web_fetch` canonical tool in `tools.py` using `httpx` with
     `allowed_domains`, `max_uses`, cost accounting in `search_cost_tokens`, and rejection of binary
     or encrypted content.
  5. Retired non-deployable `automations.py` and `test_automations.py`.
- Deferred (Phase 3b): parallel worker fan-out (def-1 declares
  execution_order sequential), streaming/resume/hooks capabilities, CMA
  interop, decomposition-audit eval zero (cookbook caveat: "the facts were
  audited; the question decomposition wasn't").
- Tests: 308 passing tests (including 7 lifecycle and invariant tests, bot decision lifecycle tests, and baseline memory persistence tests), 16/16 offline evals with
  8/8 blocking zeros holding, mypy strict clean (30 source files), ruff clean. Full gate green.

### Test Count Reconciliation (292 / 328 / 308)
- **292 baseline**: Pre-expansion Phase 3b test suite (verification gating, memory CAS, live retry). Grew to 295 with initial baseline_map memory tests.
- **328 peak (D42)**: 295 baseline + 33 unit tests in `tests/test_automations.py` validating the Automations proto wire format and Slack trigger ingestion.
- **308 authoritative (D43)**:
  - `-33` tests: Retired and deleted `tests/test_automations.py` when D43 established Slack/Automations draft scaffolding as out of scope.
  - `+7` tests: Added `tests/test_lifecycle.py` enforcing D43 runtime invariants (backend `aclose()`, lock release, runtime_kind affinity, event loop ownership).
  - `+4` tests: Added `web_search` domain constraint, binary rejection, and toolkit dispatch tests in `tests/test_tools.py`.
  - `+2` tests: Added `bot.decide()` cancel lifecycle and cross-session baseline retrieval tests in `tests/test_bot.py`.
  - **Net total: 328 - 33 + 13 = 308 tests**, all passing clean. (D42 peak of 328, minus 33 automation tests retired in D43, plus 13 replacement tests for lifecycle, web_search, and bot decision.)
## Proposed direction — feature-driven, resumable project execution (2026-11-23)

**Status: design direction recorded; not implemented.** This proposal captures the feature-oriented workflow discussed on 2026-11-23. It does not silently change the current `breakdown.yaml` definition, the eight-stage runtime, or existing persisted records. Implementation requires a separate, reviewed workflow/schema change.

### Purpose

A project-level request should first become a structured, reviewable feature backlog. Breakdown should then work on **one coherent feature at a time**, completing that feature's research, approved plan, implementation, testing, independent verification, and audit before selecting another feature. A session may complete only one feature; unfinished work must remain recoverable rather than being reported as complete or regenerated from the original request.

This is a sequential feature lifecycle, not a deferred scheduler, dependency-wave engine, or parallel build queue.

### Proposed flow

```text
USER INPUT
    |
    v
HOST-MANAGED CONTEXT GENERATION
    |
    v
FEATURE SCAFFOLDING
    |  - understand objective, target repository and constraints
    |  - decompose into coherent, independently verifiable features
    |  - establish dependencies, acceptance criteria and test intent
    v
feature_list.json (versioned proposal)
    |
    v
USER REVIEW / APPROVAL OF BACKLOG REVISION
    |
    v
SELECT ONE ELIGIBLE FEATURE
    |
    v
RESEARCHER — research the selected feature
    |
    v
AUDITOR — review research evidence and unresolved questions
    |
    v
PLANNER — implementation plan and any justified refactor proposal
    |
    v
USER REVIEW / APPROVAL OF EXACT FEATURE PLAN
    |
    v
BUILDER — implement the feature and run its tests
    |  - frontend/backend implementation as applicable
    |  - browser automation for browser-visible behavior
    |  - fix defects within the approved scope
    |  - capture execution and test evidence
    v
HOST-INVOKED INDEPENDENT VERIFICATION
    |
    v
AUDITOR — inspect resulting source, behavior and evidence
    |
    +---- Findings do not require a change
    |          |
    |          v
    |     RETAIN FEATURE EVIDENCE
    |
    +---- Correction / refactor is justified
               |
               v
          PLANNER — bounded correction/refactor proposal
               |
               v
          USER APPROVAL when plan, paths, scope or source binding changes
               |
               v
          BUILDER — implement approved correction
               |
               v
          INDEPENDENT RE-VERIFICATION
               |
               v
          AUDITOR RE-REVIEW
    |
    v
HOST RECORDS FEATURE COMPLETION AND EVIDENCE REFERENCES
    |
    v
SELECT NEXT ELIGIBLE FEATURE
```

The feature backlog approval and an individual implementation-plan approval are distinct decisions. Approval must bind the exact manifest/feature revision, plan revision, source checkpoint, authorized paths/actions, and verification criteria relevant to that decision. A changed scope or stale source binding must return to review; an agent's message is never approval.

### Feature manifest responsibilities

`feature_list.json` is the project-level feature manifest, not a second workflow definition and not a transcript of every runtime event. Its proposed contents are:

- Project identity, objective, target-repository identity, manifest schema version, and manifest revision.
- Stable feature IDs, names, descriptions, priorities, and dependency IDs.
- Feature requirements, research questions, acceptance criteria, implementation boundaries, and test intent.
- Browser scenarios where applicable, backend/API checks, and end-to-end verification expectations.
- Required capability descriptions for tool discovery; these are requests, not grants of execution authority.
- A coarse feature lifecycle status, the active feature ID, and references to the approved plan, run, findings, test results, and verification evidence.

Reports, source diffs, test output, approvals, and event history remain separate durable artifacts. The manifest references those artifacts rather than embedding large reports or duplicating the runtime journal.

**Ownership and source-of-truth rule:** the Host is the only component that changes the authoritative manifest revision or feature lifecycle status. Agents return proposed feature data, findings, plans, and results; they do not directly rewrite the manifest or runtime stores. The existing ArtifactStore/revision mechanisms should be reused where suitable rather than introducing a second persistence owner. The user-facing `feature_list.json` serialization and its eventual location must have one canonical owner; do not maintain competing editable copies.

The three records remain distinct:

| Record | Authority |
|---|---|
| `breakdown.yaml` | Executable workflow definition: stages, contracts, transitions, gates, and deterministic operations |
| `feature_list.json` | Project backlog: feature decomposition, dependencies, acceptance intent, status, and artifact references |
| `.breakdown/` runtime state | Run state, events, approvals, checkpoints, locks, artifacts, and recovery information |

### Responsibility boundaries

- **Context generation and feature scaffolding:** Host-managed intake. It may use model assistance, but the Host validates and persists the proposed manifest. This is not a new autonomous agent or a source of execution authority.
- **Researcher:** Researches the currently selected feature and returns source-grounded findings, constraints, and unanswered questions.
- **Auditor:** Performs read-only review of research, repository state, implementation changes, and verification evidence. It reports defects and architectural concerns with evidence; it does not edit source or authorize a refactor.
- **Planner:** Owns implementation design and bounded correction/refactor proposals. It cannot freeze, approve, or execute its own plan.
- **Builder:** Implements only the approved feature/plan scope, including frontend/backend work and builder-level browser/manual tests. Builder test reports are evidence, not independent authorization.
- **Verifier:** Host-invoked independent verification against the approved acceptance criteria. It is not a fifth autonomous workflow agent and cannot advance the workflow.
- **Coder:** Remains a bounded read-only capability under Auditor, not a peer agent.
- **Analyzer:** Do not add a separate autonomous Analyzer agent. Architectural analysis is part of Auditor's findings; Planner turns justified findings into a proposed design.

### Tool Discovery Service boundary

The separate Tool Discovery Service is a capability resolver used by the workflow. Given structured feature context and the current operation, it can return relevant registered tool definitions, schemas, versions, and availability information. It does not generate the feature backlog, invent executable tools, execute tools, approve plans, or advance stages.

Discovery results are candidates only. The Host must still enforce caller identity, stage/operation allowlists, tool provenance, authorization, and execution-time checks. The service remains independently deployable and must not become a second workflow authority or a Breakdown-specific dependency in its core.

### Session continuity and completion invariants

1. At most one feature is active for a project by default. Select the next feature only after its dependencies are completed and the current feature reaches the defined completion boundary.
2. A feature is a coherent vertical increment. Its frontend, backend, tests, and integration work should normally remain together when they contribute to the same user-visible capability; do not turn each layer into a separate feature merely to create more backlog entries.
3. Do not start the next feature because the current session is ending. Complete the current feature where possible; otherwise persist its exact state and resume it in the next session.
4. Resume from the existing manifest revision, active feature, run ID, approved plan binding, source checkpoint, completed research, execution attempts, test/verification evidence, Auditor findings, and unresolved questions. Do not regenerate completed work from the original user request.
5. Feature completion requires accepted criteria to be accounted for, independent verification evidence, Auditor review disposition, reconciled attempts, and retained artifact references. Builder self-report alone cannot complete a feature.
6. A refactor is not automatic. Auditor findings justify Planner analysis; a plan/scope/source change follows the applicable approval boundary before Builder acts.
7. If work is blocked or interrupted, retain that state and its evidence. Do not convert missing checks or uncertainty into completion.

### Design validation required before implementation

The feature scaffolder and lifecycle should be evaluated against at least these cases:

- A small single-feature request and a large multi-feature application request.
- Features with explicit dependencies and features that can be independently selected.
- A cross-cutting prerequisite (for example, authentication) used by later features.
- An ambiguous request where the correct action is to preserve uncertainty and ask for review, not invent requirements.
- A feature spanning UI, API/backend, persistence, and browser tests.
- Duplicate or overlapping features, circular dependencies, an overly broad feature, and a feature too small to merit its own lifecycle.
- Research that changes acceptance criteria or reveals a new dependency.
- Builder changes outside approved paths, tests that do not exercise the acceptance criteria, and browser automation that cannot run.
- Auditor findings requiring no change, a bounded in-scope correction, or a scope-changing refactor requiring renewed approval.
- Session interruption during research, implementation, verification, or audit, followed by resume without losing evidence or repeating completed operations.
- A stale manifest/plan revision or changed source checkpoint at approval or execution time.

Acceptance is behavioral: the tests must demonstrate that one feature can be taken from an approved proposal through implementation, independent verification, audit disposition, durable retention, and later-session resume, while the next feature remains untouched until the current one is complete.

### Decisions still open

- The canonical on-disk location and edit/export policy for `feature_list.json`.
- Whether context generation and feature scaffolding extend the current Auditor `research_proposal` operation or require a separately declared intake operation in a future workflow revision.
- The exact lifecycle status vocabulary and which transitions are deterministic Host operations.
- How to represent shared foundations and cross-cutting requirements without splitting a coherent feature or duplicating ownership.
- Which browser automation and other test capabilities are registered, actually executable, and authorized in each environment.

**Next step:** design the manifest schema and transition/approval bindings, then create good/bad lifecycle evaluations. Do not begin implementation by adding a new agent, copying Tool Discovery into Breakdown, or changing the existing workflow definition without a separately reviewed plan.


### Long-running feature implementation protocol (sample-derived)

This protocol makes the feature-at-a-time rule operational for multi-session application work. It is a proposed implementation discipline; it does not change the current runtime until a separately reviewed contract/schema implementation is accepted.

#### 1. Scaffold and freeze the test specification

The context/feature scaffolder produces a versioned `feature_list.json` containing stable feature IDs and stable test IDs. Each test contains its original description, ordered steps, expected visible outcomes, and an initial `"passes": false`. UI tests must describe the real user journey, not merely an API call or internal function invocation.

After the user approves a manifest revision, treat the feature and test definitions as immutable:

- The only field an implementation/verification cycle may update in `feature_list.json` is a test's `passes` boolean.
- Do not remove tests, rewrite descriptions, change steps or expected outcomes, merge/split tests, reorder tests, or silently regenerate the manifest.
- A missing, ambiguous, contradictory, or technically impossible test is recorded as a finding. Resolving it requires a separately reviewed manifest revision; it is not permission to edit the approved test in place.
- Keep the manifest revision and a digest of its immutable test specification bound to the approval. The Host verifies that a proposed update changes only `passes` for existing test IDs.
- The Host is the authoritative writer of the manifest. Agents return verification outcomes and evidence references; they do not directly edit project state.

This is intentionally stricter than treating `feature_list.json` as a general progress document. It is an approved test specification with narrowly mutable verification bits.

#### 2. Work one feature, end to end

Select one eligible feature whose dependencies are complete. Research it, resolve constraints, define/approve its implementation plan, then implement the complete vertical slice. Include frontend, backend, persistence and integration changes where the feature needs them. Do not split a user-visible feature into disconnected frontend/backend tasks merely to increase the feature count.

The Builder may test and fix its own work, but its report is not independent verification. Do not begin a second feature while the current one has unverified tests, unresolved blocking findings, or incomplete required evidence.

#### 3. Mandatory real-browser verification for UI features

For every feature with user-visible behavior, acceptance requires exercising the actual deployed/local application UI in a real browser using an authorized browser-automation tool. The test must behave like a user:

- Navigate to the application and the relevant page through the browser.
- Click visible controls; type using keyboard input; submit forms; scroll; navigate; and use the application as a person would.
- Exercise the complete user workflow from its entry point through the expected outcome, including relevant error, empty, loading, success, and recovery states specified by the test.
- Capture screenshots at each meaningful test step, including the resulting state after important interactions. Save them under a stable path such as `verification/<feature-id>/<test-id>/step-<nn>.png`.
- Inspect each screenshot against the approved design/specification and expected visual state. A screenshot merely existing is not visual verification.
- Observe browser console output during the workflow. Any console error blocks the test until investigated and resolved or explicitly dispositioned under an approved exception; do not silently filter errors.
- Record the browser, viewport, application revision/source checkpoint, test ID, step, timestamp, and screenshot artifact references in the verification record.

Do not use `curl`, direct HTTP requests, database inspection, internal function calls, or JavaScript evaluation as a substitute for user interaction. Do not use `page.evaluate`, injected scripts, direct DOM mutation, or app-state manipulation to bypass the interface. Browser automation may use normal locator/accessibility interactions, keyboard, mouse, navigation, scrolling, screenshots, and supported browser console/log APIs. API/unit/integration tests remain useful supplemental checks, never the sole acceptance evidence for UI behavior.

If a feature genuinely has no user-visible interface, do not fabricate one or mark a UI test as passing. Record the mismatch as blocked/not applicable and obtain an explicit test-spec decision through a new approved manifest revision before changing the test contract.

#### 4. Verification evidence and the `passes` update

A test can change from `"passes": false` to `"passes": true` only after all of the following are present:

1. Every prescribed step was executed against the intended application revision.
2. The expected functional result was observed through the real UI.
3. Required screenshots were captured and visually inspected.
4. Browser console errors were inspected; no unresolved errors remain.
5. The full user workflow completed, not just an isolated control or endpoint.
6. Any defects found during the run were fixed and the affected workflow was rerun.
7. Independent verification accepts the evidence; Builder self-report alone cannot flip the field.

Keep the evidence itself outside `feature_list.json` (for example in the existing Host-managed artifact store and a human-readable `verification/` export). Use stable feature/test IDs so each screenshot, browser trace, console record, source checkpoint, and verifier result can be correlated without adding fields to the frozen manifest. The Host performs a narrow update to the single `passes` field and records the before/after manifest digest and supporting artifact references in its durable event/artifact history.

A code change can invalidate a previously verified test. The Host must mark affected `passes` values false (the only permitted field mutation) when their verification is no longer valid, then require the same unchanged test steps to be rerun before setting them true again. Never leave a stale true value merely to preserve a completion count.

#### 5. Fix regressions before expanding scope

Run the relevant existing test suite before and after feature changes. Triage pre-existing failures separately from regressions. A regression blocks completion of the current feature and takes priority over starting new feature work. Do not edit, delete, weaken, skip, or reorder tests to obtain a green result. A test that cannot be executed remains not passing; missing infrastructure is not a pass.

The quality target is correctness and verified user experience, not maximizing the number of green booleans. A zero-console-error target applies to the tested workflow; performance and responsive behavior must also be checked against explicit acceptance criteria rather than vague claims such as "fast" or "polished."

#### 6. Commit a verified feature as a coherent checkpoint

After the feature's required tests have been independently verified:

- Stage only the intended implementation files, verification artifacts, and the approved `passes` changes. Do not use an indiscriminate `git add .`; inspect the working tree and staged diff to avoid including unrelated user changes, secrets, temporary files, or generated artifacts.
- Commit with a feature-specific message that identifies the implementation and its evidence. The commit should identify the feature, tests exercised, browser verification, and manifest pass-bit updates.
- Retain the commit SHA, source checkpoint, verification report, screenshot references, and manifest revision in the run record.
- Update the existing living `PLANS.md` milestone/retrospective when the implementation plan or durable project direction changes. Runtime session progress, resumable state, and event history belong to the existing Host-managed `.breakdown/` stores.

Do not create parallel `work-progress.txt` and `claude-progress.txt` files as competing progress authorities. If a future human-readable handoff projection is needed, derive it from the canonical run/feature records or designate exactly one generated projection with a clear owner.

#### 7. End the session without losing state

Prefer ending a session immediately after one feature reaches its verified completion boundary. Before stopping, ensure:

- The active feature ID, manifest revision, plan/approval bindings, source checkpoint, commit SHA, and current test counts are durable.
- Every completed test has its screenshot and verification evidence retained, and only those test `passes` values are true.
- Incomplete or blocked tests remain false with a specific reason and next action recorded outside the manifest.
- Defects, unresolved risks, and the next eligible feature are recorded in the run handoff.
- The application is left in its last known usable state; do not hide an unfinished or broken state behind a passing flag.

If interrupted before feature completion, persist an explicit resumable checkpoint and keep incomplete tests false. Do not start the next feature. A checkpoint commit may be used when repository policy requires committed session progress, but it must be clearly identified as incomplete and must not imply feature completion. Never discard unrelated or pre-existing working-tree changes to manufacture a clean state.

#### 8. Per-feature acceptance record

The Host should be able to produce a compact record equivalent to:

```text
Feature: FEAT-###
Manifest revision: <revision>
Approved plan: <artifact-ref + digest>
Source checkpoint: <commit/checkpoint>
Tests: <verified>/<total>
Browser: <browser + version>
Viewport(s): <tested viewport(s)>
Screenshots: verification/<feature-id>/<test-id>/
Console: <observed errors and disposition>
Independent verifier: <result + evidence ref>
Auditor review: <findings + disposition>
Commit: <commit SHA>
Next action: <next feature or explicit blocker>
```

The test count is calculated from the immutable test IDs and current `passes` values; it is never hand-edited. A feature is complete only when every required test is passing on the retained source checkpoint, independent verification and Auditor review are recorded, and no blocking finding remains.

#### Scenarios required to validate this protocol

- Agent attempts to edit a test description, step, order, expected result, or any field other than `passes`: Host rejects the manifest mutation.
- Agent claims a UI test passed using only `curl`, an API client, or JavaScript evaluation: Host rejects the pass-bit update.
- Screenshot is missing, captured at the wrong step, or not visually reviewed: test remains not passing.
- Browser console contains an unresolved error: test remains not passing.
- One step fails: fix the product, rerun the affected workflow, and retain both failure and corrected-run evidence.
- A later code change affects an earlier passing test: Host invalidates the affected pass bit and requires re-verification.
- Session ends mid-feature: resume the same feature from its durable checkpoint; do not select the next feature.
- A new requirement or incorrect test specification is discovered: preserve the approved manifest and request a separately reviewed revision.
- Working tree contains unrelated user changes: stage only explicitly owned paths and preserve the unrelated changes.
- All feature tests are green but independent verification or Auditor review is missing: feature remains incomplete.


## Agent Middleware Architecture Decision (2026-11-24)

**Status:** Accepted architectural direction for future design. This is a decision record, not implementation authorization.

### Purpose

Give each Agent extensible interception points around its internal model calls and tool executions without duplicating Agent execution loops or transferring workflow authority from System Runtime.

### Terminology and boundary

A **workflow stage** is one of the eight stages declared in `breakdown.yaml` (for example, `research_proposal`, `research_approval`, and `research_execution`). An **Agent middleware stage** is an internal interception point inside one Agent invocation. These are different concepts and must not be conflated or represented as additional workflow stages.

An Agent middleware stage has a typed context (the data entering that operation) and a typed result (the data returned from it). Middleware handlers execute in three fixed phases, independent of the order in which different phases are registered:

1. **Input** — transforms the stage context before the operation runs.
2. **Wrap** — surrounds the operation and receives the context plus a `next` callable. Calling `next` zero times short-circuits the operation; once runs it normally; more than once repeats it and therefore requires explicit retry/replay policy.
3. **Output** — transforms or inspects the typed stage result after the operation.

The phase order is always Input → Wrap → operation → Output. Within a phase, registration order determines handler nesting; the first registered Wrap handler is outermost.

### Initial interception points

Start with two actual execution boundaries:

- **`InvokeModelStage`:** around one provider/model invocation. Its context can carry the prepared model input and call-scoped metadata; its result represents that model invocation's typed response.
- **`ExecuteToolStage`:** around one requested tool execution. Its context carries the normalized tool request and Host-bound dispatch context; its result represents the tool execution result.

Do not create arbitrary/custom middleware stages by default. Add another interception point only when a real shared execution boundary needs it.

### API and placement

The shared middleware machinery belongs at `breakdown/agent/middleware.py`: stage tokens, phase/context/result types, handler typing, registration, and deterministic dispatch.

The shared Agent execution entry point exposes instance-scoped registration, conceptually:

```python
agent = ResearcherAgent(config=config)
agent.add_middleware(InvokeModelStage.Input, be_concise)
result = await agent.run(approved_research_input)
```

This is an API direction, not an existing implementation signature. Middleware registration is scoped to the Agent instance unless a separately justified requirement establishes another scope.

Agent-specific contracts remain owned by each Agent and are defined in its own `agent.py`. Do not add `breakdown/agent/contracts.py` or `breakdown/agent/shared/base.py`. The shared context/result types in `middleware.py` describe interception mechanics; they do not define Researcher, Auditor, Planner, Builder, or Verifier domain contracts.

The existing `breakdown/contracts.py` is a current workflow-contract module. This decision does not remove, rename, or repurpose it.

### Authority and execution constraints

- System Runtime continues to own the eight-stage workflow, stage progression, user approval gates, durable state, execution budgets, and completion.
- Middleware cannot approve a research proposal or implementation plan, advance workflow state, persist authoritative artifacts, synchronize repository changes, or grant capabilities.
- The Host constructs and injects the ToolGateway. Middleware cannot replace or override the Host-bound caller identity, Agent identity, allowlist, repository root, memory root, credentials, or other authority-bearing context.
- Input middleware may transform call-scoped model input, but must not silently remove mandatory Agent instructions, provenance requirements, or evidence constraints.
- Output middleware cannot bypass Agent-specific schema validation or Runtime evidence validation.
- Wrap retries must be bounded. Repeating a model call may incur cost; repeating a tool call may repeat an external side effect. Tool-stage repetition therefore requires explicit idempotency/replay semantics and must not be enabled by generic middleware behavior.
- Errors and cancellation must remain observable. Middleware must not turn an exception, missing result, or uncertain execution into a valid result.

### Relationship to Agent context

Temporary conversation context belongs to the Agent invocation. Any future context-management capability (including token-pressure reporting, summarization, truncation, and pinning) belongs under `breakdown/agent/capabilities/` and may use middleware where appropriate.

That capability must not own cross-run MemoryStore persistence, workflow state, approvals, source-checkpoint identity, or authoritative repository evidence. Durable memory remains System Storage-owned. Context summaries are working context, not substitutes for source evidence or artifact references.

### Relationship to the current implementation

At the inspected baseline, `OpenAICompatibleRoleBackend.generate()` combines the bounded model/tool-call loop and direct canonical-tool dispatch. This does not yet provide independent model-invocation and tool-execution interception points.

Implementation must first establish one shared bounded Agent execution loop, separate provider request/response transport from loop orchestration, and route tool execution through the Host-created ToolGateway. Middleware must wrap those real boundaries; callbacks around the existing aggregate `generate()` method would not provide the intended semantics.

The current CLI remains the single application entry point at `breakdown/__main__.py`. Workflow approval and resume remain Runtime operations; they are not implemented as Agent `start()`, `send()`, `end()`, or `resume()` methods.

### Required behavioral validation before implementation is accepted

- Input handlers run before Wrap and transform only the supplied stage context.
- Wrap handlers receive the correct context and `next`; tests cover zero, one, and multiple calls with bounded retry behavior.
- Output handlers receive and return the stage's declared result type.
- Phase order is fixed regardless of cross-phase registration order; handler nesting within each phase is deterministic.
- Middleware registered on one Agent instance does not leak into another Agent instance.
- Model-call middleware and tool-execution middleware intercept their respective individual operations, not merely the outer Agent invocation.
- Tool authorization is rechecked by the Host at dispatch; middleware and model output cannot alter the immutable caller identity or data roots.
- Repeated tool execution cannot duplicate non-idempotent effects without an explicit replay/idempotency policy.
- Middleware cannot bypass Agent schema validation, user approvals, Runtime budgets, sandbox containment, persistence ownership, or synchronization authorization.
- Cancellation, exceptions, short-circuits, and retry exhaustion are represented truthfully and leave sufficient evidence for Runtime handling.

### Non-goals

This decision does not add dependencies, adopt Strands internals as a dependency, implement a persistent conversational session API, change `breakdown.yaml`, change the eight workflow stages, rename current source modules, or authorize the planned Agent/System package migration. The Strands middleware design is a reference pattern; Breakdown owns its own small compatible contract and implementation.

### References

- [Strands middleware API and phase semantics](https://github.com/strands-agents/harness-sdk/blob/main/strands-py/src/strands/agent/agent.py)
- [Strands middleware stage/context types](https://github.com/strands-agents/harness-sdk/blob/main/strands-py/src/strands/middleware/stages.py)
- [Current Breakdown bounded model/tool loop](https://github.com/itz1508/Breakdown/blob/763f763b3ed3f45019d342eb9b1a901ae44b38b7/breakdown/live_backend.py)
- [Current Breakdown workflow definition](https://github.com/itz1508/Breakdown/blob/763f763b3ed3f45019d342eb9b1a901ae44b38b7/breakdown.yaml)
