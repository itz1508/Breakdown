# Breakdown — Current Architecture and Workflow

**Updated:** 2026-11-24  
**Status:** Current design baseline / target architecture. This document supersedes the older feature-manifest workflow proposal and earlier conflicting agent-role descriptions. It records intended behavior; it does not claim that the repository has already been migrated.

## 1. Purpose and operating model

Breakdown processes a user request through specification, research, repository reconciliation, planning, explicit package confirmation, and controlled build execution.

The operating model is:

- **Python performs the work.**
- **JSON carries saved state, handoffs, artifacts, and results.**
- The existing application, model/tool interfaces, APIs, and Storage connect and persist the workflow.
- The application/Runtime owns workflow authority, decisions, authorization, resume, and lifecycle.
- Agents perform bounded role work and return typed results and artifact references. They do not advance the workflow, approve their own work, or own persistence.

Do not add a second controller, scheduler, storage system, or role-specific handoff schema. Reuse existing application interfaces, identity records, artifact formats, digest functions, and persistence where they fit.

## 2. Current target package structure

```text
breakdown/
├── __init__.py
├── __main__.py                   # only entry point; builds the agents dict
├── tests/                        # layering, cross-agent contracts, workflow-level
├── shared/
│   ├── __init__.py
│   ├── base.py
│   ├── config.py
│   ├── models.py
│   └── tests/
├── agents/
│   ├── __init__.py               # explicit imports
│   ├── loop.py                   # shared model loop
│   ├── prompt.py
│   ├── researcher/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── SKILL.md
│   │   └── tests/
│   ├── auditor/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── SKILL.md
│   │   └── tests/
│   ├── coder/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── SKILL.md
│   │   └── tests/
│   ├── planner/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── SKILL.md
│   │   └── tests/
│   └── builder/
│       ├── __init__.py
│       ├── agent.py
│       ├── SKILL.md
│       └── tests/                # Builder does not use the shared model loop
└── system/
    ├── runtime/
    │   ├── __init__.py
    │   └── sandbox.py
    ├── storage/
    ├── tools/
    ├── memory.py
    ├── safety.py
    └── tests/
```

### 2.1 Five independent roles

There are five independently constructible and dispatchable roles:

1. Researcher
2. Auditor
3. Coder
4. Planner
5. Builder

Each role owns its behavior, domain input/output contract, skill guidance, and focused tests. **Coder is an independent role** under `agents/coder/`; it is not `auditor/coder.py`, an Auditor-owned sub-role, or a sixth workflow authority.

Being an independent role does not confer workflow authority. Runtime decides when a role may run, which inputs and capabilities it receives, and whether its result is current and acceptable. Auditor and Coder communicate through the shared handoff and versioned artifact references, not direct control of one another.

The exact operation(s) that activate Coder must be mapped to the executable workflow and its existing contracts. Do not infer that Coder has Builder's source-writing or sandbox permissions merely from its name. Its capabilities must be explicit and Host-authorized.

### 2.2 Composition, shared code, and dependency boundaries

- `breakdown/__main__.py` is the only application entry point and composition root. It builds the explicit agents dictionary and injects configuration, clients, backends, tools, and other capabilities.
- Construction must happen through callable functions. Importing a module must not instantiate an agent, read credentials, or perform external work.
- `shared/` contains cross-role contracts, configuration types, and shared artifact models only. `shared/base.py` defines minimal contracts/protocols; it must not become a universal Agent superclass or an inheritance framework.
- `agents/loop.py` contains the shared model/tool loop for roles that use it. Agent-specific behavior and domain contracts remain in each role's `agent.py`.
- Builder does not use the shared model loop. It receives its required coding/execution capability through dependency injection; no capability is hidden inside Runtime.
- Do not add a new `providers/` package or provider abstraction as part of this restructuring. Reuse and inject existing backend interfaces and implementations unless source inspection demonstrates a concrete gap and a separate design is approved.
- Do not introduce the previously proposed shared Input → Wrap → Output middleware framework. That proposal is withdrawn.
- Agents may import shared contracts and consume injected capabilities. They must not import sibling agents or own Runtime/Storage.
- Runtime may invoke agents through explicit contracts. Storage must not import agents. Shared modules must not import upward into agents or system.
- Keep internal Runtime and Storage models in their owning components. Move only genuinely cross-boundary models into `shared/models.py`.
- The root package tests layering and cross-agent behavior. Each role keeps focused tests. System keeps Runtime, Storage, Tools, and safety-related tests.

### 2.3 System ownership

| Component | Owns |
|---|---|
| `system/runtime/` | Workflow coordination, role activation, user-decision enforcement, progression, resume, execution authorization, sandbox lifecycle, and terminal handling. |
| `system/storage/` | Durable artifacts, revisions, events, runs, checkpoints, and other persisted state using the existing persistence owner. |
| `system/tools/` | Canonical tool definitions, registration, dispatch, and integration with Runtime authorization. |
| `system/memory.py` | Memory operations/interface; durable memory persistence remains Storage-owned. |
| `system/safety.py` | Safety boundary, path containment, source-drift checks, synchronization safeguards, and related enforcement. |
| `system/runtime/sandbox.py` | Sandbox lifecycle implementation under Runtime authorization. |

Independent verification, when selected, is a System/Runtime-controlled operation. It is not a sixth autonomous agent and cannot change workflow state or Builder results.

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

```text
Session start or resume
  ↓
User input
  ↓
Auditor prepares specification → discovery.json
  ↓
Streamed specification preview
  ├─ Agent edit / manual edit / add or remove detail → new revision and preview
  ├─ Declined → retain decision and relevant artifacts → Completion (no Build)
  └─ Accept & Check
       ↓
     Auditor checks the exact accepted specification
       ├─ Material issue → clarification or edit
       │    → review changed content → Accept & Check again
       └─ Ready
            ↓
          Application records/awaits explicit user approval
            ↓
          Researcher investigates accepted research items
            ↓
          Auditor reconciles research against the physical repository
          and records the source checkpoint
            ↓
          Planner creates the implementation plan, TaskTodo,
          dependencies, acceptance criteria, and fixture definitions
            ↓
          Planner runs applicable plan checks and fixture validity checks
            ├─ Research defect / invalid fixture → Researcher
            │    → affected derived results superseded
            │    → Auditor reconciliation and Planner work repeat
            └─ Checks are ready
                 ↓
               Assemble, hash, and retain the exact package
                 ↓
               Remove only unreferenced preparation scratch
                 ↓
               Final plan/package preview
                 ├─ Changes requested → preserve prior package
                 │    → supersede affected results → revise
                 │    → repeat affected checks → new package/digest
                 │    → renewed preview and confirmation
                 ├─ Declined → retain decision/artifacts
                 │    → clean disposable material → Completion (no Build)
                 └─ User confirms the exact package
                      ↓
                    Builder verifies package hashes and source preconditions
                      ├─ Mismatch → stop before sandbox creation
                      │    → preserve artifacts and supersede affected results
                      │    → Auditor reconciliation → Planner → new package
                      │    → renewed user confirmation
                      └─ Preconditions match
                           ↓
                         Create authorized sandbox
                           ↓
                         Execute TaskTodo asynchronously
                           ↓
                         Run assigned checks
                           ↓
                         Retain execution evidence
                           ↓
                         Synchronize actual authorized results
                           ↓
                         Finalize build.json, checkpoint,
                         and synchronization_result
                           ↓
                         Preserve recovery material
                           ↓
                         Clean disposable execution intermediates
                           ↓
                         Exit/release sandbox
                           ↓
                         Completion records actual outcome
```

No sandbox and no application-source change may occur before the exact package has been confirmed and its hashes and source preconditions have been verified.

## 5. Role responsibilities and outputs

| Owner | Responsibility |
|---|---|
| Existing application / Runtime | Start or resume the existing thread/session/run; load pending decisions and current artifact references; record user decisions; validate handoffs; dispatch roles; persist authoritative state; enforce transitions and authorization. |
| Auditor — specification | Read the request and available context; separate facts, inferences, suggestions, and unknowns; produce `discovery.json`; support streamed, revision-preserving specification review. |
| User through the application | Review Item, Requirements, Current State, and Research Items; edit individual content, request an agent revision, Accept & Check, approve when ready, request plan changes, confirm the exact package, or decline. |
| Auditor — specification check | Compare the exact accepted specification revision with the original request; identify contradictions, unsupported additions, missing decisions, and material issues; return ready only when the check supports it. |
| Researcher | Investigate accepted research items; gather source-grounded evidence; record contradictions, alternatives, limitations, and unknowns; return artifact references and questions. |
| Auditor — repository reconciliation | Inspect research and the physical repository; trace callers and dependencies; identify actual gaps, scaffolding relationships, and preservation requirements; record the source checkpoint and evidence. This is a read-only source-review responsibility. |
| Planner | Turn current evidence into implementation decisions, phases, file-level operations, TaskTodo, dependencies, acceptance criteria, and fixture definitions. Run applicable plan checks and assemble the exact package. |
| Coder | Operate as an independent, explicitly dispatched role under its own contract and authorized capabilities. Do not collapse it into Auditor or silently assign it Builder's sandbox execution authority. Its concrete workflow activation point must be represented by an approved operation/contract. |
| Builder | Verify confirmed package hashes and source preconditions; create the authorized sandbox; execute TaskTodo; run assigned checks; retain evidence; synchronize actual results; finalize Builder outputs; preserve recovery material; exit the sandbox. |
| Optional independent verifier | When selected by Runtime, inspect the confirmed package, Builder outputs, checkpoint, and execution evidence; return a separate `validation_result`. It does not repeat Builder execution or mutate `build.json`. |

### 5.1 Research and reconciliation artifacts

Use the existing artifact consumer formats and reference mechanisms. The current workflow references these generated outputs:

- `audit.json`: findings, evidence, contradictions, limitations, and unknowns.
- `code.json`: evidence-supported technical options, APIs, dependencies, and relevant code information.
- `fixture.json`: fixture requirements, supplied inputs, and expected observable behavior.
- `case_samples.json`: matched GOOD and BAD cases whose expectations are supported by evidence.

These are artifacts, not new storage systems. Verify their actual schemas, ownership, and consumers against the current source before implementation; do not invent replacement formats where the application already has one.

## 6. The confirmed package

The package contains exact versioned references to:

- Original request and accepted specification.
- Specification-check result.
- Research artifacts.
- Auditor repository findings and scaffolding map.
- Source checkpoint.
- Plan revision and implementation plan.
- Phase steps and TaskTodo.
- Dependencies and acceptance criteria.
- Fixture definitions and plan/fixture check results.

The user confirms the package reference, package digest, plan revision, and source checkpoint. Confirmation applies to those exact contents, not to a mutable plan label.

### 6.1 Package digest

The package digest is SHA-256 over RFC 8785 canonical JSON of the ordered list of package references, with each reference carrying its artifact digest.

- Key order and insignificant whitespace must not affect the digest.
- Any content change must produce a different artifact digest and therefore a different package digest.
- Reuse the existing canonicalization and digest functions. If an RFC 8785 library is already used, do not create a custom canonicalizer.
- Preserve historical packages. A new revision does not overwrite the package that was previously reviewed or confirmed.

## 7. Currency, invalidation, and supersession

A result is **current** only when every input reference and digest recorded for that result still matches the present input. Work that finishes after one of its inputs changes is marked superseded on arrival and must not be consumed as current.

Only results derived from changed content are superseded. Historical results remain readable; unaffected results stay current.

| Changed input | Results superseded | Resume/repeat from |
|---|---|---|
| Original request or accepted specification content | Specification check; research derived from it; repository reconciliation; plan; package | Specification check |
| Research artifacts | Repository reconciliation; plan; package | Repository reconciliation |
| Source checkpoint / in-scope repository change | Repository reconciliation; plan; package | Repository reconciliation |
| Plan or TaskTodo | Plan-check results; package | Plan checks |
| Fixture definitions | Fixture/plan-check results; package | Plan checks |

Clarification resumes only affected work. Do not regenerate completed current research or restart unrelated stages.

## 8. Fixture validity

A fixture is valid only when the existing fixture check establishes that:

- Required inputs are present and readable.
- Each expected observation is supported by research evidence.
- GOOD and BAD cases are distinguishable by the check assigned to evaluate them.

An invalid fixture blocks package readiness. Trace the cause to the research result that supplied it. When the defect is in research evidence, return the work to Researcher; do not ask Planner to invent supporting evidence. Supersede the affected research-derived results, then repeat repository reconciliation and planning as required.

## 9. Source checkpoint and drift scope

Use the existing checkpoint format. The source checkpoint records:

- Repository revision identity.
- A digest for every file the confirmed package reads or changes.
- The traced dependencies relevant to those files.

Source preconditions are met when the repository identity and all in-scope digests still match at Build start.

Differences outside this defined drift scope are recorded but do not, by themselves, block execution. Do not silently expand the drift scope to the entire repository.

### 9.1 Drift before Build

If an in-scope file differs from the confirmed checkpoint, or a confirmed artifact fails its hash check:

1. Stop before creating any sandbox.
2. Preserve the confirmed package and all relevant artifacts.
3. Mark affected derived results superseded.
4. Return to Auditor repository reconciliation.
5. Re-plan and assemble a new package.
6. Obtain renewed user confirmation of the new exact package.

A previous confirmation does not authorize changed content.

### 9.2 Drift during Build

If execution changes a file that TaskTodo does not authorize, or a change cannot safely be attributed to the current execution:

1. Stop further work at a safe point.
2. Preserve partial results and execution evidence.
3. Record the effects as uncertain.
4. Finish the Builder result record and recovery information.
5. Do not claim success. Completion classifies the actual outcome.

## 10. Builder execution, retry, and cancellation

### 10.1 Execution behavior

The existing application controls asynchronous execution. Expected implementation changes are the effects authorized by the confirmed TaskTodo and actually produced by the current execution. Record actual observed results; do not infer them from the plan.

A failed TaskTodo item or assigned check does not automatically suppress synchronization of already-authorized actual results. Record each failed or unfinished item in `build.json`; the outcome cannot be succeeded while required work remains incomplete.

### 10.2 Retry

Retry failed or uncertain items with the same confirmed package only after:

- Uncertain effects have been reconciled.
- Source preconditions have been verified again.
- Completed work is not repeated blindly.

Any TaskTodo change requires a new package, a new digest, and renewed user confirmation. A partially executed TaskTodo is never blindly replayed.

### 10.3 Cancellation

- Before Builder starts, cancellation is handled like declining the package: retain the decision and relevant artifacts; create no sandbox.
- After Builder starts, stop at the next safe point, preserve partial results and recovery material, reconcile uncertain effects, finalize Builder outputs, release the sandbox, and record the outcome as cancelled.
- Cleanup must not remove artifacts or state needed to explain or recover the partial execution.

## 11. Builder outputs and completion

### 11.1 Required Builder outputs

- **`build.json`:** Builder's returned JSON in the existing application consumer format. It records actual TaskTodo outcomes, assigned-check outcomes, implementation changes, errors, unknown/uncertain effects, execution-evidence references, and sandbox exit result.
- **Checkpoint:** Identifies the actual observed state. It records the source revision against which assigned checks ran and the revision observed after synchronization. A checkpoint is evidence of state, not an outcome and not proof of success.
- **`synchronization_result`:** Records whether actual results were transferred. Synchronization does not prove that every TaskTodo item or check succeeded.

### 11.2 Cleanup order

**Before Build:** retain the confirmed package and digest, source checkpoint, downstream research, fixture definitions, review decision, all referenced artifacts, and recovery references. Remove only unreferenced preparation scratch and disposable temporary exports.

**After Build:** before deleting anything or releasing the sandbox, finalize `build.json`, capture the checkpoint, record `synchronization_result`, and preserve execution evidence, partial/failed/uncertain effects, and recovery information. Then remove only disposable execution intermediates and exit the sandbox.

Generated artifacts are not disposable merely because they were generated. Cleanup must never delete current or historical referenced artifacts.

### 11.3 Terminal outcomes

Completion is application handling after Builder reaches a terminal state and exits the sandbox. The actual outcome is one of:

- `succeeded`
- `partial`
- `failed`
- `uncertain`
- `cancelled`

**Succeeded** requires all of the following:

1. Every required check assigned by the confirmed acceptance criteria executed.
2. Observed results match the fixture's expected observations.
3. Evidence is bound to the exact source revision against which the checks ran.
4. The post-synchronization revision equals the revision that was checked.

Anything less is partial, failed, or uncertain as supported by the evidence. Completion must never upgrade incomplete, skipped, unknown, or uncertain work to succeeded.

Completion records the `build.json` reference, checkpoint, `synchronization_result`, actual outcome, failed/unfinished work, uncertain effects, cleanup outcome, recovery information, and historical/superseded references. It does not imply that all TaskTodo items succeeded, unperformed checks passed, synchronization proved correctness, independent validation occurred, or uncertain effects were resolved.

A declined specification or package completes before Builder. Record the user decision and retained artifacts; no implementation outcome applies because nothing was built.

## 12. Optional independent verification

Independent validation is optional, not a mandatory workflow stage. When Runtime selects it, the verifier reads the confirmed package, `build.json`, checkpoint, and execution evidence and produces `validation_result`.

It may re-run read-only assigned checks against the checkpointed state. Those observations belong only in `validation_result`. It does not:

- Repeat Builder execution.
- Start a second Builder evidence cycle.
- Change `build.json`.
- Advance the workflow or authorize synchronization.

Completion remains valid without this optional verification.

## 13. Gates and authority rules

- Researcher starts only after specification review/check is ready and the application has recorded the required user approval.
- Builder starts only after the exact package is confirmed by a recorded user decision and hashes/source preconditions verify.
- A model statement is not user acceptance, plan confirmation, or cancellation. The application records the actual user decision.
- Material specification edits require review of the changed content.
- A missing input produces a question and exact `resume_at`; clarification resumes only affected work.
- Corrections return to the role that owns the affected result.
- Historical artifacts are preserved; only derived results affected by changed inputs are superseded.
- Uncertain write effects are reconciled before retry.
- Declining a specification or package terminates before Builder.

## 14. Constraints and explicit non-goals

- One shared handoff structure; no role-specific handoff schemas.
- Five independent roles; Coder is not an Auditor sub-role.
- Runtime owns workflow transitions, user approvals, activation, authorization, execution admission, and recovery.
- Storage remains the sole durable persistence owner.
- No new controller, scheduler, or storage system.
- No new provider package or provider abstraction as part of this restructuring.
- No shared middleware framework based on the withdrawn Input → Wrap → Output proposal.
- No mandatory Verifier stage and no sixth autonomous Verifier agent.
- No sandbox or application-source change before exact package confirmation and source-precondition verification.
- No feature-manifest / feature-at-a-time backlog workflow as the current orchestration model. The earlier `feature_list.json` proposal and its immutable test-pass-bit protocol are superseded and must not be treated as active requirements.
- Completion never upgrades partial, failed, skipped, unknown, or uncertain work to success.

## 15. Verification required before implementation

Re-check the current repository source before moving or replacing modules. In particular, verify:

- The application's actual handoff status values and thread/session/run/step identity binding.
- The existing `build.json` consumer format and checkpoint format.
- The exact existing reference and digest functions, including RFC 8785 canonicalization.
- The existing fixture-validity check and its consumers.
- The actual function names and operation contracts corresponding to the workflow steps.
- Current role/backend interfaces and the least-privilege capabilities each role requires.
- The actual source-checkpoint and changed-path mechanisms, including treatment of files outside drift scope.
- Existing Storage ownership and cleanup/recovery behavior.

Do not create replacement schemas or modules before this inspection. The target tree is an architectural destination; migration must preserve existing behavior and reuse existing interfaces where appropriate.

## 16. End-to-end test plan

Run against the real application, Storage, and state interfaces using a temporary workspace containing a small real Git repository. Use the existing model interface with deterministic scripted responses. Record user decisions through the application's decision-recording mechanism. Inject file tampering, process termination, and cancellation at controlled points.

### Invariants checked in every scenario

- Every role handoff validates against the one shared handoff shape.
- No sandbox exists and application-source files remain unchanged until the exact package is confirmed and preconditions pass.
- Every artifact records input references and digests.
- Superseded artifacts remain readable.
- No cleanup removes a referenced artifact or recovery material.
- Recorded outcome never exceeds the evidence.

### Required scenarios

| ID | Scenario | Required behavior |
|---|---|---|
| W01 | Complete run | Gates occur in order; user confirms exact package; Builder outputs and checkpoint are retained; outcome is derived from required checks and revision evidence. |
| W02 | Specification edit loop | Agent edits, manual edits, detail additions/removals each preserve prior revisions; changed content is checked again. |
| W03 | Specification check issue | Clarification and changed-content review occur; exact `resume_at`; Researcher does not start prematurely. |
| W04 | Specification declined | Decision is retained; no research, sandbox, or build starts. |
| W05 | Stale specification check | Specification changes while check runs; stale result is superseded on arrival and not used. |
| W06 | Missing research input | Researcher asks a question and sets exact `resume_at`; only affected work resumes. |
| W07 | Invalid fixture / research defect | Cause is traced to research; Researcher corrects it; dependent reconciliation, plan, and package are repeated. |
| W08 | Package changes requested | Old package remains readable; affected checks rerun; new digest/package requires renewed confirmation. |
| W09 | Package declined | No sandbox or source change; decision and artifacts retained; disposable preparation scratch may be cleaned. |
| W10 | Unrecorded confirmation | Model claims approval but application has no user decision; Builder is blocked. |
| W11 | Artifact tampering | Confirmed artifact digest mismatch stops before sandbox creation. |
| W12 | Drift inside scope | In-scope source file differs; stop before sandbox; reconcile, re-plan, and reconfirm. |
| W13 | Drift outside scope | Unrelated file difference is recorded but does not alone block Build. |
| W14 | Unauthorized mid-build change | Stop further work; preserve partial evidence; record uncertain effects; outcome is not succeeded. |
| W15 | Failed assigned check | Authorized actual results are handled according to synchronization policy; failure is recorded; outcome is partial or failed. |
| W16 | Required check skipped | Outcome cannot be succeeded. |
| W17 | Post-sync revision mismatch | Outcome cannot be succeeded. |
| W18 | Partial execution and retry | Reconcile uncertain effects and re-check preconditions; do not repeat completed items; TaskTodo change requires new confirmation. |
| W19 | Cancellation during Build | Stop at safe point; preserve recovery material; release sandbox; outcome cancelled. |
| W20 | Crash and resume | Kill at each durable step; resume using `resume_at`; reuse current results and do not duplicate completed work. |
| W21 | Digest stability | Reordered object keys/whitespace do not change canonical digest; changed content does. |
| W22 | Cleanup safety | Success, failure, and cancellation retain all referenced evidence and recovery material. |
| W23 | Optional verifier | Completion works with or without independent verification; when used, `validation_result` is separate and `build.json` stays unchanged. |
| W24 | Role independence and layering | All five roles can be constructed/dispatched independently; Coder is not imported through Auditor; no forbidden agent-to-agent or shared-to-system imports. |
| W25 | Composition root | Importing modules has no construction/credential/network side effects; the one entry point builds the injected agents dictionary. |

A test is meaningful only when a deliberate violation of the protected behavior makes that test fail. Do not describe the workflow as implemented or verified until these checks have been run against the actual current source.
