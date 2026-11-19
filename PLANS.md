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
  4. Researcher web access: client-side `web_search` canonical tool in `tools.py` using `httpx` with
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
  - **Net total: 295 - 33 + 7 + 4 + 2 = 308 tests**, all passing clean.


