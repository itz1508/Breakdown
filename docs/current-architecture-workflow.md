# Breakdown — Target Architecture and Workflow

**Updated:** 2026-11-24  
**Status:** Intended target baseline — not a claim about the current executable workflow or migrated source layout. The current eight-stage implementation on `main` is described in [docs/workflow.md](workflow.md) and [docs/architecture.md](architecture.md).

## 1. Purpose and operating model

Breakdown processes the user's actual input through specification preparation and review, accepted-item research, evidence comparison, planning, explicit approval, controlled Builder execution, independent validation, and completion.

The operating model is:

- **The user supplies intent; agents do not invent it.**
- **Python performs the work.** JSON carries durable state, handoffs, artifacts, and results.
- **Host owns orchestration:** workflow authority, dispatch, approvals, confirmation/hash checks, resume, cancellation, and lifecycle.
- **Storage owns persistence:** artifact revisions, run state, checkpoints, and retained history.
- The five agent skills perform bounded work and return typed results and artifact references. They do not advance the workflow, approve their own work, or own persistence.
- The project work tree organizes implementation independently of the runtime workflow.
- Independent verification is a Host-controlled operation, not an agent role. Its invocation interface, backend contract, and result persistence must be defined against actual source; this target does not prescribe a module or public function name.

Do not add a second controller, scheduler, storage system, or competing progress authority. Reuse existing application interfaces, identity records, artifact formats, digest functions, and persistence where they fit.

## 2. Target package structure

```text
repository/
└── breakdown/
    ├── __main__.py
    ├── agent/
    │   └── skills/
    │       ├── auditor/
    │       ├── researcher/
    │       ├── planner/
    │       ├── coder/
    │       └── builder/
    ├── shared/
    │   └── queue/
    │       └── TaskTodo             # shared work representation, not a scheduler
    ├── system/
    │   ├── host/
    │   │   ├── workflow_control.py
    │   │   ├── confirmation_verify.py
    │   │   └── skill_dispatch.py
    │   ├── storage/
    │   │   ├── package_store.py
    │   │   ├── artifact_store.py
    │   │   └── revision_store.py
    │   └── ...
    ├── mcp/
    │   └── tools/                   # preserve existing breakdown/mcp/tools convention
```

This is the intended ownership layout, not a statement that these paths already exist on `main`. Preserve current module conventions and map source owners before moving or creating files.

### 2.1 Five independently dispatched agent skills

The target has five independently dispatched agent skills:

1. Auditor
2. Researcher
3. Planner
4. Coder
5. Builder

Each skill owns bounded behavior, domain guidance, and relevant input/output contracts. Host decides when a skill may run and which inputs and capabilities it receives. A skill cannot activate siblings, approve work, change permissions, or advance the workflow.

- **Auditor** prepares the specification and performs evidence comparison.
- **Researcher** investigates accepted research items.
- **Planner** designs the implementation, constructs the project work tree, and resolves planning gaps.
- **Coder** performs explicitly assigned code-oriented analysis or operations under its own contract and Host-authorized capabilities. It is independent of Auditor and does not inherit Builder sandbox authority.
- **Builder** executes the user-approved TaskTodo in the authorized sandbox, exports actual results, and exits.

Independent validation is not another autonomous agent. Host invokes a separately configured verifier capability after Builder exports and exits; its result is retained separately from Builder's execution output. The actual invocation interface and backend contract must be grounded in existing source.

### 2.2 Composition and dependency boundaries

- `__main__.py` is the application entry point/composition root. Construction is callable and dependency-injected; imports must not instantiate skills, read credentials, open Storage, or perform external work.
- `system/host/` owns workflow control, skill dispatch, user-decision enforcement, confirmation/hash verification, lifecycle, recovery, cancellation, and transitions.
- `system/storage/` owns durable artifacts, immutable snapshots, revisions, and run history. Do not create duplicate persistence owners.
- `shared/queue/TaskTodo` is a shared work representation. It is not a deferred scheduler, dependency-wave engine, batch queue, or phase barrier.
- Agent skills consume shared contracts and injected capabilities. They do not import sibling skills or Host/Storage internals.
- Preserve MCP tools under the existing `breakdown/mcp/tools/` convention. Hooks are a separate SDK integration mechanism; do not duplicate hooks as MCP tools or invent a hook directory without inspecting the SDK and repository.
- Builder does not use the shared model/tool loop. Its coding/execution capability is injected and constrained by the confirmed TaskTodo.
- Host controls the independent validation operation after Builder export/exit. Its implementation must reuse a source-backed verifier/backend interface; do not invent a module path, function name, or sixth agent.
- Do not introduce a new provider package, universal Agent superclass, controller, scheduler, or withdrawn Input → Wrap → Output middleware framework.

### 2.3 Host and Storage ownership

| Component | Owns |
|---|---|
| `system/host/` | Workflow authority, skill activation, approval enforcement, confirmation/hash checks, transitions, resume, cancellation, sandbox lifecycle, and recovery. |
| `system/storage/` | Durable artifact, immutable revision, run, checkpoint, and history persistence using the existing persistence owner. |
| `breakdown/mcp/tools/` | Registered MCP tool schemas and dispatch integrations under the existing package convention. |
| Hooks | SDK lifecycle/event interception where supported; separate from MCP tool registration. |
| `shared/queue/TaskTodo` | Shared task representation and task-level coordination data; not a deferred job queue. |
| Independent verifier/backend | Bounded validation only; no workflow authority, plan mutation, Builder execution, or self-approval. |



## 3. One shared handoff

Every role uses the same logical handoff shape:

```json
{
  "role": "researcher",
  "status": "completed",
  "input_refs": [],
  "output_refs": [],
  "resume_at": null,
  "questions": []
}
```

The application binds the handoff to the actual thread, session, run, and step identities. Each role keeps its internal phases and instructions outside the handoff.

Rules:

- Reuse the application's existing `status` vocabulary; do not invent new handoff status values.
- Every input/output reference identifies the artifact version and digest using the existing reference format.
- `resume_at` identifies the exact point where affected work can continue.
- `questions` carries unresolved information requests. A response resumes only affected work.
- The application/Runtime persists and validates handoffs. Agents return them; agents do not write the authoritative run state.
- Do not create per-role handoff schemas.

## 4. End-to-end workflow

The runtime workflow has a small number of meaningful phases. These describe user-facing progression, owners, decisions, and return paths. They are not file-level implementation tasks.

```text
01. Session Start or Run
          |
          v
02. User Input
          |
          v
03. Auditor prepares discovery.json
          |
          v
04. Specification Revision and Accept & Check
          |-- Agent/manual edits, additions, removals → preserved revision + preview
          |-- Decline → retain decision → Completion (no Research or Build)
          |-- Accept & Check → Auditor checks that exact revision
          |       |-- Material issue → clarification/edit → new preview → Accept & Check again
          |       |-- Valid → continue
          v
05. Researcher investigates accepted research items
          |
          v
06. Auditor post-research evidence comparison
          |
          v
07. Planning
    - Code review and refactor design
    - Coder operations when explicitly required
    - Fixture and test definitions
    - Scanner final gap analysis
    - Implementation Plan and project TaskTodo
          |
          v
08. User Review and Approval
    - Bind approval to exact plan revision + source checkpoint
    - Changes → responsible prior work, then review again
    - Decline → Completion without Builder
          |
          v
09. Confirmation, Hash Check, and Builder Execution
    - Verify approval, artifact hashes, and source preconditions
    - Host starts the authorized sandbox
    - Builder executes approved TaskTodo, exports results, and exits
          |
          v
10. Independent Validation and Completion
    - Host invokes an independent validation operation that does not rely on Builder self-report
    - Findings return to the responsible owner for correction
    - Completion retains evidence, decisions, and recovery state
```

There is no additional user-approval gate between a valid specification check and Researcher. The user-facing implementation approval occurs after Planning and binds the exact Implementation Plan revision and source checkpoint. Do not add a separate feature-list approval or a second user-approval gate.

**Specification behavior**

- Every agent edit, manual edit, addition, removal, or clarification creates a new immutable specification revision.
- Every revision change produces a preview of the changed content.
- Accept & Check evaluates the exact submitted revision against the original user input and available evidence.
- A material issue returns to clarification/editing; the changed content is previewed and must be checked again.
- Declining the specification retains the decision and artifacts and completes without Research or Build.

**Approval and Build behavior**

- User Review & Approval binds the exact Implementation Plan revision and source checkpoint.
- A requested change returns to the responsible research, audit, or planning work; affected outputs are refreshed and presented for approval again.
- Host verifies the recorded approval, artifact hashes, and in-scope source preconditions before creating the sandbox.
- Builder executes only the approved TaskTodo, exports actual results, and exits the sandbox.
- After Builder export and sandbox exit, Host invokes an independent validation operation through a separately configured verifier capability. Builder self-reported checks are not independent validation. The exact callable, input/output contract, backend configuration, and result persistence remain to be mapped to existing source before implementation.
- A changed approved plan or source checkpoint requires renewed user review and approval before another Build.



## 5. Role responsibilities and outputs

| Owner | Responsibility |
|---|---|
| Application / Host | Start or resume the session/run; receive actual User Input; restore current decisions and references; dispatch the five agent skills; validate handoffs; enforce approvals and hash/source checks; invoke independent verification; own transitions, cancellation, and recovery. |
| Storage | Persist immutable artifacts, revisions, source checkpoints, task results, validation evidence, and run history. |
| Auditor — specification | Read the actual user input; distinguish explicit requirements from facts, assumptions, inferences, suggestions, and unknowns; prepare `discovery.json`; stream revision-preserving previews. |
| User through the application | Edit or clarify the specification; Accept & Check or decline; later review and approve the exact Implementation Plan revision and source checkpoint. |
| Auditor — evidence comparison | Check the exact accepted specification; after Research, compare findings with accepted intent and relevant physical repository evidence; return grounded findings. |
| Researcher | Investigate accepted research items; collect source-grounded evidence; record provenance, contradictions, alternatives, limitations, missing context, and unresolved questions. |
| Planner | Review code, design refactoring, define implementation scope, create the project work tree and TaskTodo, define fixtures/acceptance criteria, resolve planning gaps, and incorporate Scanner's final gap analysis. |
| Coder | Execute only explicitly assigned code-oriented analysis/operations through its own contract and Host-authorized capabilities. It cannot approve, advance the workflow, or acquire Builder sandbox authority by implication. |
| Builder | Execute TaskTodo in the authorized sandbox; record actual operations and effects; export actual results; exit the sandbox. Builder does not perform or claim independent validation. |
| Independent verifier/backend | Host invokes the separate verifier capability after Builder export/exit. It evaluates the exported result against approved criteria and returns a separate validation result. It cannot rewrite Builder output, change the plan, or advance the workflow. The actual interface must be source-grounded. |
| Scanner capability | Perform the final bounded gap analysis during Planning and return findings to Planner. It is not a workflow authority or a user-approval owner. |

### 5.1 Research and reconciliation artifacts

Use the existing artifact consumer formats and reference mechanisms. The target workflow may use:

- `discovery.json`: versioned user specification and reviewable content.
- `audit.json`: findings, evidence, contradictions, limitations, and unknowns.
- `code.json`: evidence-supported technical options, APIs, dependencies, and relevant code information.
- `fixture.json`: fixture requirements, supplied inputs, and expected observable behavior.
- `case_samples.json`: matched GOOD and BAD cases whose expectations are supported by evidence.
- Implementation Plan and TaskTodo artifacts: approved work scope, task ownership, dependencies, and verification criteria.
- Builder export and separate validation result: separate records of execution and independent validation.

These are artifact names from the target design, not proof that their schemas or consumers already exist on `main`. Verify actual schemas, ownership, and consumers against source before implementation. Do not invent replacement formats when the application already has one.

### 5.2 Project work tree and parallel execution

Planning creates a tree-shaped work breakdown:

```text
Project
  ├── Phase 01
  │     ├── Task 001 → one target file → To-do (1–3 steps)
  │     ├── Task 002 → one target file → To-do (1–3 steps)
  │     └── ... approximately 10 tasks
  ├── Phase 02
  │     └── ...
  └── Phase 10
        └── ...
```

A useful planning scale for a substantial project is approximately 10 work phases with approximately 10 file tasks per phase (around 100 tasks across the project). This is a sizing guide, not a quota. Use fewer or more phases/tasks when actual scope requires it. These are project work items, not 100 workflow stages.

**Task and To-do rules**

1. One implementation task owns exactly one target file. A change spanning five files creates five file tasks.
2. Each task has a short objective and a To-do list of 1–3 concrete guidance steps. Do not expand it into keystroke-level instructions or hundreds of micro-steps.
3. Inspect the result, run the task's focused verification, record actual evidence, and mark the task done. A plan-only response is not completion.
4. One agent can own multiple file tasks. Around 5–10 files per agent is normal when capability, complexity, and context permit; it is not a hard limit.
5. Multiple agents may execute independent file tasks concurrently. At least five concurrent file tasks is the normal target when enough independent work exists.
6. Only one active writer may own a target file. Establish shared interfaces before parallel work that depends on them.
7. Dispatch independent ready tasks immediately. Honor real dependencies, but do not impose artificial phase barriers, dependency waves, batches, or deferred queues.
8. Runtime workflow phases and project work phases are different structures; do not force a one-to-one mapping.
9. The Implementation Plan and TaskTodo are the planning layer. Do not require a separate Stage Plan for every file task or every 1–3-step To-do.

Example file task:

```text
Task 024
  Target file: breakdown/system/host/workflow_control.py
  Owner: Agent A
  To-do:
    1. Inspect the current owner and its callers.
    2. Implement the approved bounded change.
    3. Run focused verification and record the observed result.
  Completion: inspect diff + evidence, then mark done.
```

The current `BuildTask` contract on `main` can carry multiple `target_paths` in one task. That current capability does not satisfy the target one-file-per-task granularity. Migration must split cross-file work into separate tasks and update the corresponding contracts, validators, dispatch, and tests; documentation must not claim this behavior is already implemented.



## 6. User approval and integrity verification

The user-facing approval object is the exact Implementation Plan revision and source checkpoint. Do not add a separate feature-list approval or a second user-approval gate.

The approved plan references the evidence needed to execute the work:

- Original user input and checked `discovery.json` revision.
- Accepted research artifacts and Auditor evidence comparison.
- Repository findings and source checkpoint.
- Implementation Plan revision and project work tree.
- TaskTodo, dependencies, acceptance criteria, fixtures, and relevant verification definitions.
- Artifact revisions and digests needed to establish currency.

Storage retains the referenced immutable artifacts. User approval binds the exact plan revision and source checkpoint. Artifact digests support integrity and currency checks; they do not multiply user decisions.

Before Builder starts, Host verifies:

- An explicit application-recorded user approval exists.
- The approval binds the exact Implementation Plan revision and source checkpoint.
- Every required artifact reference exists and its digest matches.
- Repository identity and in-scope source hashes still match the approved checkpoint.
- Each task's file scope and required capabilities remain within the approved plan.

A change to the approved plan, TaskTodo scope, acceptance criteria, or in-scope source checkpoint requires a new plan revision, refreshed dependent evidence, and renewed user approval. A previous approval never authorizes changed content. Reuse the existing SHA-256 and RFC 8785 canonical JSON implementations where required; do not introduce a parallel digest mechanism.

## 7. Currency, invalidation, and supersession

A result is current only while every recorded input reference and digest still matches. A result produced after one of its inputs changes is superseded on arrival and cannot be consumed as current.

Preserve history and supersede only results derived from changed inputs.

| Changed input | Supersede | Resume/repeat from |
|---|---|---|
| Original user input or accepted specification | Specification check and all dependent research, evidence comparison, planning, and approval artifacts | Specification check |
| Research result | Dependent evidence comparison, planning, fixtures, and approval artifacts | First affected research/reconciliation work |
| Source checkpoint or in-scope source file | Repository reconciliation, affected plan/tasks, and approval | Auditor repository reconciliation |
| Implementation Plan or TaskTodo | Affected task assignments, verification definitions, and approval | Planning and user review |
| Fixture/test definition | Dependent plan checks and approval | Planning |

Do not repeat unaffected current work merely because another result was superseded.

## 8. Fixtures and evidence

Create fixture definitions only when a real input exists or repeatable behavior requires one. Record the actual fixture source, input, trigger, expected state, observable output, assertion, failure condition, and provenance.

A fixture is usable only when required inputs are present and expected observations are supported by evidence. If evidence is missing or a fixture is invalid, return the gap to its source owner; Planner must not invent supporting facts.

Fixtures, mocks, manifests, reports, and sandbox artifacts do not by themselves prove live production behavior. Use the verification surface appropriate to the requirement: actual browser interaction for UI behavior; the declared API, CLI, library, or runtime interface for other behavior.

## 9. Source checkpoint and drift

Use the existing checkpoint format. It records repository identity and digests for the files in approved scope plus relevant traced dependencies. The exact scope must be derived from inspected source and the approved plan; do not silently widen it to the entire repository.

Before Builder starts, Host verifies that the repository identity and in-scope file digests still match the approved checkpoint.

If an in-scope file or required artifact no longer matches:

1. Stop before creating the sandbox.
2. Preserve the approved plan and all referenced artifacts.
3. Supersede only dependent evidence and planning results.
4. Return to Auditor repository reconciliation.
5. Refresh affected planning work and create a new plan revision.
6. Obtain renewed user approval bound to the revised plan and checkpoint.

A previous approval does not authorize changed content. Out-of-scope drift is recorded but does not automatically expand approved work.

During Builder execution, an unauthorized or unattributable mutation requires a safe stop. Preserve partial output, evidence, and uncertain effects; do not blindly replay or revert them.

## 10. Builder execution, retry, and cancellation

Builder starts only after Host verifies the recorded user approval, artifact hashes, and source preconditions. Host creates the authorized sandbox and injects only approved task inputs and least-privilege capabilities.

Builder executes the approved TaskTodo in its defined order, records actual operations and outcomes, exports its result, and exits the sandbox. Builder cannot silently add, reorder, or skip approved tasks.

Each implementation task owns one target file. If an additional file or behavior is needed, stop that out-of-scope work and return it to Planning. A change to approved scope requires a new plan revision and renewed user approval.

Retry is allowed only after uncertain effects are reconciled, completed work is not repeated blindly, and source preconditions are checked again. Cancellation preserves partial results and recovery evidence, exits the sandbox safely, and records the actual cancellation outcome.

## 11. Builder export and retention

Builder's export records actual TaskTodo outcomes, changed files, errors, uncertainty, execution evidence, and sandbox exit result using the verified consumer contract.

Host and Storage retain the export, checkpoint, task results, source references, and recovery material. Any synchronization/transfer is authorized and recorded by the existing Host/Safety policy. Synchronization proves transfer only; it does not prove correctness.

Do not delete referenced artifacts or recovery-critical material. Cleanup may remove only disposable intermediates after their retained outputs and references are secured.

## 12. Independent validation

Independent validation is a required target phase after Builder exports the result and exits the sandbox. Host invokes a separately configured verifier capability with the exact approved plan revision, source checkpoint, Builder export, and required criteria. The operation returns a separate validation result containing checks performed, observed results, evidence references, and remaining findings. It is not another autonomous agent.

**Current implementation boundary on `main`:** `breakdown/verification.py` contains helper functions for assembling verification input, building a backend request, parsing verifier responses, and deriving a failure reason. It is not a standalone verification runner. `WorkflowEngine._post_build` contains an optional verifier-backend branch, but `breakdown/bootstrap.py` does not register a default verifier backend. The existing tests exercise the branch by injecting fake verifier backends; they do not prove default wiring. Consequently, independent validation is not active in the default runtime.

The target migration must specify and test the actual verifier construction and invocation, backend configuration, input/output contract, evidence binding, and result persistence by inspecting and reusing current source owners. Do not assume a missing runner, invent a function name, or describe the target operation as already implemented.

The independent verification operation does not:

- Repeat Builder execution or modify the Builder export.
- Change Builder's execution record.
- Change the approved plan, expand scope, or grant capabilities.
- Synchronize files, approve the work, or advance the workflow by itself.

A missing validation result is not equivalent to valid verification. A `not_valid`, `unknown`, or `blocked` required observation returns affected work to the responsible owner. A change to approved scope requires a revised plan and renewed user approval before another Build.

## 13. Completion and terminal outcomes

Completion retains the user input, specification revisions, user decisions, research, audit evidence, Implementation Plan, TaskTodo, source checkpoint, Builder export, independent validation result, and recovery references.

It records completed, failed, skipped, blocked, unfinished, and uncertain work using the application's existing status vocabulary. Do not invent incompatible persisted status values.

A result is `succeeded` only when:

1. Every required task and acceptance check has an actual recorded result.
2. The independent verifier operation ran against the exact Builder export and approved criteria, and all required observations are `valid`.
3. Evidence is bound to the exact approved Implementation Plan revision and source checkpoint.
4. Any authorized synchronization/transfer is bound to the same verified result.
5. No required work, blocking finding, or uncertain effect remains unresolved.

A declined specification completes without Research or Build. A declined Implementation Plan completes without Builder. Neither decline is reported as an implementation success.

## 14. Gates and authority rules

- User input is the sole source of user intent; agents must not manufacture requirements or implementation scope.
- Researcher starts after Accept & Check validates the exact accepted specification. There is no additional approval gate before Research.
- User Review & Approval occurs after Planning and binds the exact plan revision and source checkpoint.
- Builder starts only after recorded approval and successful artifact/source hash verification.
- Host invokes independent verifier after Builder export and sandbox exit.
- A model statement is not user acceptance, approval, confirmation, or cancellation.
- Corrections return to the owner of the affected result.
- Historical artifacts remain readable; only dependent results are superseded.
- Uncertain effects are reconciled before retry.

## 15. Constraints and explicit non-goals

- Five independently dispatched agent skills: Auditor, Researcher, Planner, Coder, and Builder. None owns workflow authority.
- Independent verification is a Host-invoked utility, not a sixth agent or workflow authority.
- Host owns workflow transitions, approvals, dispatch, confirmation/hash checks, sandbox lifecycle, and recovery.
- Storage remains the sole durable persistence owner.
- No new controller, deferred scheduler, duplicate storage owner, dependency waves, batches, or artificial phase barriers.
- No separate Stage Plan for each file task or each 1–3-step To-do; Implementation Plan and TaskTodo are the planning layer.
- No new provider package or provider abstraction as part of this restructuring.
- No shared middleware framework based on the withdrawn Input → Wrap → Output proposal.
- No sandbox or source mutation before exact plan approval and confirmation/hash verification.

## 16. Verification required before implementation

Re-check current repository source before moving or replacing modules. Verify:

- Existing handoff status values and thread/session/run/step identity binding.
- Existing TaskTodo/BuildTask consumer format and how multi-file targets are represented.
- The actual schemas and consumers for `discovery.json`, research/audit artifacts, Builder export, checkpoint, and validation result.
- Existing reference and digest functions, including RFC 8785 canonicalization.
- Actual operation contracts and workflow definitions.
- Role/skill backends and least-privilege capabilities.
- Source checkpoint, changed-path detection, synchronization, cleanup, and recovery ownership.
- Storage ownership and existing MCP/hook conventions.
- Exact way `independent verifier operation` is invoked against the exported result.

Do not create replacement schemas or modules before this inspection. The target tree is an architectural destination; migration must preserve existing behavior and reuse existing interfaces where appropriate.

## 17. End-to-end test plan

Test against the real application, Storage, and state interfaces with deterministic scripted skill responses and a temporary repository.

| ID | Scenario | Required observation |
|---|---|---|
| W01 | Complete run | Exact specification check, accepted research, evidence comparison, planning, one plan/checkpoint approval, Builder export/exit, independent verifier, and evidence-backed Completion. |
| W02 | Specification edits | Agent edits, manual edits, additions/removals preserve prior revisions and produce changed-content previews. |
| W03 | Specification check issue | Material issue returns to clarification/edit; Researcher does not start until the new exact revision passes Accept & Check. |
| W04 | Specification decline | Decision/artifacts retained; no Research, sandbox, or Build. |
| W05 | Stale check | A specification changed during checking supersedes the stale result. |
| W06 | Missing research input | Researcher asks a concrete question and records exact `resume_at`; only affected work resumes. |
| W07 | Research/evidence defect | Finding returns to Researcher or Auditor according to ownership; dependent planning is refreshed. |
| W08 | Plan change requested | Prior revisions remain readable; affected work is revised; exact new plan/checkpoint requires renewed approval. |
| W09 | Plan declined | No Builder sandbox or source change; decision and evidence retained. |
| W10 | Unrecorded approval | Builder is blocked when no application-recorded approval binds the exact plan revision/checkpoint. |
| W11 | Artifact tampering | Hash mismatch stops before sandbox creation. |
| W12 | In-scope source drift | Stop before sandbox; reconcile source, revise plan, and obtain renewed approval. |
| W13 | Out-of-scope drift | Record without silently expanding blocking scope. |
| W14 | Unauthorized mid-build change | Safe stop; preserve partial/uncertain evidence; do not claim success. |
| W15 | Required task/check not run | Record as not run; outcome cannot be succeeded. |
| W16 | Independent validation missing or errors | Missing/failed verifier invocation cannot be treated as valid. |
| W17 | Independent validation rejects export | Return findings to the responsible owner; changed approved scope requires renewed approval. |
| W18 | Export/verification revision mismatch | Outcome cannot be succeeded. |
| W19 | Partial execution and retry | Reconcile uncertain effects, preserve completed tasks, and do not blindly replay. |
| W20 | Cancellation during Build | Stop safely, preserve recovery material, release sandbox, and record cancellation. |
| W21 | Crash and resume | Reuse current results and resume only affected work without duplicate execution. |
| W22 | Digest stability | Canonical digest ignores key order/whitespace changes and detects content changes. |
| W23 | Cleanup safety | Current/historical referenced artifacts and recovery evidence remain retained. |
| W24 | Skill independence/layering | Five skills dispatch under Host authority; Coder is independent of Auditor; no forbidden skill-to-skill or shared-to-system imports. |
| W25 | Composition root | Imports have no construction/credential/network side effects; entry point builds the injected skill registry. |
| W26 | File-level task tree | Each implementation task owns one target file and has 1–3 To-do steps. |
| W27 | Parallel execution | Independent tasks execute concurrently; agents can own multiple tasks; at least five concurrent tasks are targeted when available. |
| W28 | Dependency behavior | Only real dependencies delay tasks; no artificial phase barriers, waves, batches, or deferred queues. |
| W29 | Task writer ownership | No two active writers modify the same file; every completed task has inspected output and verification evidence. |

A test is meaningful only when a deliberate violation of the protected behavior makes it fail. Do not describe the target workflow as implemented or verified until these checks have run against the actual source.

