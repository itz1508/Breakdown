# Breakdown — Accepted Target Architecture and Workflow

**Repository:** itz1508/Breakdown  
**Target model:** six independent agents; Host owns orchestration and authorization; Storage owns persistence.  
**Document role:** target architecture record, not a claim that the current executable workflow has already been migrated.

## 1. Authority and implementation status

- Current explicit user decisions define the target.
- Physical repository source, runtime behavior, and tests establish what is currently implemented.
- Git history and older project documents provide migration evidence, not authority over newer decisions.
- External references teach patterns only; they do not authorize copying their architecture, code, dependencies, provider assumptions, or workflows.

At the main baseline inspected for this migration, the repository had five implemented agents: Researcher, Auditor, Coder, Planner, and Builder. Builder was nested under Planner, Discovery did not exist, and the executable breakdown.yaml described an older eight-stage workflow with Auditor proposal creation and a separate Research approval. This branch relocates Builder to breakdown/builder/ and adds common prompt assembly. It does **not** yet implement/register Discovery or replace the existing workflow/runtime. Do not describe the six-agent workflow as operational until its contracts, dispatch, lifecycle and tests are migrated.

## 2. Independent agent packages

The target has six sibling agent packages:

- **Discovery:** prepares the structured, revisionable specification from the actual user request.
- **Researcher:** investigates only accepted research items; preserves evidence, provenance, contradictions and unknowns.
- **Auditor:** checks the exact accepted specification and later performs final package review; does not select architecture.
- **Planner:** owns evidence comparison, technical design, gap resolution, project decomposition, fixtures and verification planning.
- **Coder:** independent bounded code analysis or explicitly authorized code operations; not an Auditor sub-role.
- **Builder:** executes only the confirmed package in the authorized sandbox, exports actual changes and exits.

Each agent owns its __init__.py, agent.py, its request/response contracts, and its role-specific instructions. The six agents are not nested under a common agent/skills package. Builder is a sibling of Planner.

### Shared support, not another agent

- breakdown/agents/prompt.py assembles shared source-grounded instructions with the agent's colocated SKILL.md.
- breakdown/agents/tools/ is the target home for provider-independent agent-facing tool adapters and contracts. Host owns tool registration, dispatch and authorization.
- breakdown/shared/queue/TaskTodo is a shared work representation, not a deferred scheduler.
- breakdown/skills/verify_all.py is an independent Host-invoked verification capability, not a seventh agent.

The shared framework does not confer capabilities. A skill describes how an agent should work; the Host/runtime determines which operations can actually be called.

## 3. Workflow

1. **Session Start/Resume** — Host restores the durable run/session context and verifies required bindings.
2. **User Input** — preserve the user's actual request and constraints.
3. **Discovery** — prepare the first structured discovery.json specification.
4. **Specification Revision and Preview** — agent edits, manual edits, additions, removals and clarifications create immutable revisions; each changed revision gets a changed-content preview. Earlier revisions remain available.
5. **Accept & Check** — submit the exact selected Discovery revision to Auditor. Auditor checks that exact revision. A material issue returns to clarification/edit; changed content must be previewed and submitted through Accept & Check again. Accept & Check is not implementation approval.
6. **Decline** — retain the decision and artifacts and complete without Research or Build.
7. **Research** — Researcher investigates only accepted research items and returns normalized evidence, provenance, contradictions, limitations and unresolved information. There is no separate Research approval gate.
8. **Post-research evidence comparison** — Planner compares accepted requirements with research evidence and the repository evidence.
9. **Planning** — review existing code, design/refactor, run Coder operations when required, define fixtures and verification, perform the final bounded read-only PlanningGapScan, resolve material gaps, and prepare the project/task package. Scanner is a capability consumed by Planner, not a seventh agent or workflow stage.
10. **Auditor final package review** — review the exact plan/package and its traceability, unresolved items, file scope and verification coverage.
11. **User Review and Approval** — bind explicit approval to the exact package/plan revision and source checkpoint. Requested changes return affected work for revision and review. Decline completes without Builder.
12. **Host confirmation and integrity checks** — verify the approval binding, package digest, source checkpoint and current authorization. This is deterministic Host enforcement, not a second user approval.
13. **Builder** — execute only confirmed work in the authorized sandbox, capture actual operations and observations, export the resulting changes and exit.
14. **Independent Validation** — Host invokes skills/verify_all.py against exported results and accepted requirements. Builder's self-report is not independent validation.
15. **Completion and Retention** — Host reconciles execution/verification evidence, records the actual outcome and retains eligible artifacts.

No agent advances the workflow or invokes the next workflow owner directly. Host controls every transition, pause, resume, cancellation and completion.

## 4. Work decomposition and execution

The project work breakdown is:

**Project → Phases → Tasks → TaskTodo**

- Phases group coherent project outcomes; they are not workflow stages.
- Tasks are independently understandable, bounded work items with requirement traceability, a clear owner and verification.
- A task's To-do is short guidance for completing that task, normally one to three steps; it is not a scheduler or a deferred queue.
- Dependencies determine ordering. Independent tasks may proceed concurrently only when the Host/runtime and exclusive file ownership permit it.
- Use one active writer per file; establish shared contracts before dependent tasks.
- Do not invent a fixed task/phase count, dependency waves, scheduling queues, or artificial barriers.
- Builder works only from the confirmed package and the authorized sandbox scope. It cannot add, reorder or skip confirmed tasks.

The present implementation still uses ImplementationPlan/BuildTask records. Migration to the accepted TaskTodo work representation is not established by this document or by the Builder relocation alone.

## 5. Agent authority boundaries

| Agent | Owns | Must not own |
|---|---|---|
| Discovery | User request decomposition, initial specification, revisionable edits and previews | Auditor checks, architecture selection, workflow control, implementation approval |
| Researcher | Accepted research, source retrieval, provenance, evidence normalization, contradictions and unknowns | Scope expansion, architecture selection, source mutation |
| Auditor | Exact-revision specification check, evidence reconciliation and final package review | Initial specification authoring, architecture selection, build task creation, execution |
| Planner | Evidence comparison, technical decisions, gap analysis/resolution, project decomposition, fixtures and verification criteria | User approval, source execution, workflow transitions |
| Coder | Bounded code evidence and authorized code operations defined by its contract | Auditor ownership, plan approval, workflow transitions, self-granted write access |
| Builder | Confirmed sandbox execution, actual observations and export | Plan mutation, added paths, permission grants, synchronization authorization, independent verification or completion |

**PlanningGapScan** is read-only and bounded. It checks requirement evidence, unresolved research, repository impact, interfaces/dependency decisions, requirement-to-task traceability, fixtures and verification coverage. Host controls its invocation; Planner interprets findings and owns corrections.

## 6. Authorization and IETF Intent Token concepts

Use the IETF Intent Token draft as design input, not as an adopted standard or a requirement to implement OAuth/JWT machinery.

- User intent, agent interpretation, specification acceptance and implementation approval are distinct records/events.
- The exact approved package revision and source checkpoint form the upper authorization boundary.
- Agent metadata and skills may declare capability requirements; they never grant permissions.
- Host evaluates resource + action + constraints for each invocation. Invocation authority may be narrower than the approved envelope, never broader.
- Enforce deterministic checks before dispatch. LLM review may flag anomalies but must not override deterministic denial.
- Track cumulative budgets/quotas across invocations when the approved work has aggregate limits; checking each call independently is insufficient.
- Sensitive operations use the Host's exact-action confirmation path.
- Cancellation or invalidated approval prevents subsequent authorized operations.
- Reuse existing approval, digest, checkpoint and Storage owners; do not create duplicate authorization stores.
- Do not introduce JWT, OAuth Token Exchange, Proof-of-Possession or an external PDP unless a real cross-boundary integration requires them.

The current repository has role-level canonical-tool allowlists, plan approval hashes, source checkpoint binding, workflow budgets and deterministic synchronization checks. It does not yet expose a fully run-bound InvocationGrant at the canonical dispatch boundary; do not claim that it does.

## 7. Shared source-grounded working method

All agent prompts combine the shared framework in breakdown/agents/WORKING_FRAMEWORK.md with the agent's own SKILL.md.

The common method requires:
- inspect user intent, source context, repository/ref and available tools before action;
- distinguish facts, derived results, inference, assumptions and unknowns;
- ground implementation claims in physical source/runtime/tests and external behavior in official sources;
- retain exact evidence locators and source identity;
- report readiness separately from criterion results and execution states;
- produce findings with issue, evidence, reference and effect, and propose correction only when needed;
- use typed structured outputs, not invented JSON fields;
- use fixtures as repeatable tests, not as proof of live product behavior;
- use evaluator–optimizer feedback only for explicit criteria and bounded iterations;
- avoid automatic delegation for trivial tasks and avoid overlapping specialist work;
- continue implementation and verification only within approved scope and available capability.

A fixed feature_list.json with 200 entries is not a Breakdown requirement. Test coverage must derive from accepted requirements, risk and observable behavior. Synthetic cases can supplement, not replace, reviewed acceptance criteria and real execution evidence.

## 8. Target package layout

    breakdown/
    ├── __init__.py
    ├── __main__.py
    ├── discovery/{__init__.py, agent.py}
    ├── researcher/{__init__.py, agent.py}
    ├── auditor/{__init__.py, agent.py}
    ├── planner/{__init__.py, agent.py}
    ├── coder/{__init__.py, agent.py}
    ├── builder/{__init__.py, agent.py}
    ├── agents/
    │   ├── __init__.py
    │   ├── prompt.py
    │   └── tools/
    ├── shared/
    │   └── queue/
    │       └── TaskTodo
    ├── system/
    │   ├── host/
    │   │   ├── workflow_control.py
    │   │   ├── confirmation_verify.py
    │   │   └── skill_dispatch.py
    │   └── storage/
    │       ├── package_store.py
    │       ├── artifact_store.py
    │       └── revision_store.py
    └── skills/
        └── verify_all.py

This is the accepted target layout, not the current physical package tree. Existing Runtime, canonical tools, shared models, tests and CLI must be migrated by inspecting their actual consumers and preserving behavior—not by creating parallel owners or assuming the destination files already exist.
