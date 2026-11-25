# Breakdown — Latest Workflow and Package Structure

**Updated:** 2026-11-25  
**Status:** Target baseline for the rebuild. This document describes the intended structure and workflow; it does not claim that the current executable source has already been migrated.

This revision supersedes the earlier five-independent-skill target. Breakdown has **four agents**: Researcher, Auditor, Planner, and Builder. Coder remains a read-only supporting capability inside Auditor.

## 1. Operating model

Breakdown processes the user's actual input through specification preparation and review, accepted-item research, evidence comparison, planning, explicit approval, controlled Builder execution, independent validation, and completion.

- The user supplies intent; agents do not invent it.
- Python performs the work. JSON carries durable state, handoffs, artifacts, and results.
- Runtime owns workflow progression, approval enforcement, confirmation and hash checks, resume, cancellation, and lifecycle.
- Storage owns durable persistence.
- Four agents perform bounded work and return typed results and artifact references. They do not advance the workflow, approve their own work, or own persistence.
- Independent verification is a runtime-controlled operation after Builder export and exit. It is not a fifth agent.
- The project work tree organizes implementation independently of the runtime workflow.

Do not add a second controller, scheduler, storage system, or competing progress authority. Reuse existing application interfaces, identity records, artifact formats, digest functions, and persistence where they fit.

## 2. Stage contract

Every stage opens with a recorded plan, runs only that plan, proves its results with evidence, and hands off through a gate.

1. **Entry check.** Inputs are present with their digests, tools and sources are reachable, and the authority for each claim is identified. The result is `valid` (proceed), `uncertainty` (a bounded part can proceed; name the exact unsupported part), or `blocked`. Difficulty alone never blocks.
2. **Plan.** Write the phase plan, then the task to-do, before any action. The Builder's plan is the confirmed to-do list the Planner wrote: it cannot add, reorder, or skip a task.
3. **Execute.** Execute only what the plan lists. New work enters the plan first, with a Decision Log entry giving the reason.
4. **Evidence.** Record exact commands and results. Anything not run is reported `not_run`.
5. **Report and hand off.** Use the shared stage report. A gate follows wherever a user decision is required.
6. **Next stage.** It starts at step 1 with its own plan.

A plan is never the deliverable when implementation was requested: the stage plans, then executes in the same pass, and pauses only at a gate or a stop condition.

Stop conditions: scope complete; user cancellation; unavailable access or tooling; missing required source; a product decision; or continuing would risk unsupported or destructive work. A blocked report identifies what produced the blocker, which action is blocked, why, evidence, impact, and next action.

## 3. End-to-end flow

Two user decisions bound the work: approval of the feature list and confirmation of the exact package before every build.

1. User input and session start/resume.
2. Auditor prepares the specification as `discovery.json`.
3. The user reviews the streamed, revision-preserving edit preview. Agent edits, manual edits, and add/remove-detail operations preserve prior revisions.
4. Decline retains the decision and completes without Build. Accept & Check asks Auditor to check the exact accepted specification. A material issue returns to clarification/edit; changed content must be reviewed and accepted again.
5. Researcher investigates accepted research items.
6. Auditor compares research findings with repository evidence.
7. Planner creates the phase plan and task to-do, scans gaps, and prepares the exact package.
8. The user confirms the exact package revision and source checkpoint.
9. Builder verifies hashes and preconditions, executes the confirmed to-do in the authorized sandbox, exports results, and exits.
10. Independent validation checks the exported result. Completion retains the evidence-supported outcome.

Steps 3–8 repeat for each feature. A defect or refactor returns to Planner at the planning step. A corrected to-do list receives a new hash and requires new confirmation. The correction-loop cap remains an open decision; do not invent one.

## 4. Four-agent ownership and stage plans

### Auditor

Auditor prepares the specification, explores sources, and compares findings with repository evidence. It does not select implementation architecture or create build tasks.

Before source exploration, its recorded plan identifies the objective and likely evidence sources, separates independent reads from dependent reads, batches independent reads using host-supported tools, avoids rereading unchanged material, and expands the search only when new evidence justifies it.

Coder is a read-only supporting capability inside Auditor for bounded code interpretation. It owns no workflow stage, does not independently dispatch, does not select implementation, and does not receive Builder sandbox authority.

### Researcher

Researcher investigates accepted research questions and patterns. It inspects actual source before recommending changes, researches official patterns when external technical knowledge is required, compares observed implementation with applicable patterns, distinguishes defects from optional improvements and unknowns, and preserves contradictions.

Before research, it breaks the request into concepts, entities and relationships; facts or data needed; time/context constraints; user priorities; and required answer form. It states the perspectives to cover and how findings will be synthesized, scaled to the task. Code-referenced but unprovided inputs are reported as `missing_context`.

### Planner

Planner owns the phase plan, task to-do, gap analysis, design decisions, and approved work record.

Its order is: write the phase to-do with all requirements for a usable result; review code proposals against the four criteria and their Verification sections; analyze and fix gaps; run the final gap/chaos review; create the to-do; hash it; and run preflight.

A task's proposed fields are: id, traced requirement, objective, protected behavior, scope boundary, steps, verification command and expected result, expected failure behavior, and observable success. The plan does not prescribe unverified files, folders, APIs, schemas, dependencies, or architecture.

### Builder

Builder executes the confirmed to-do in order, inside the authorized sandbox. It does not add, reorder, or skip tasks and does not invent host capabilities.

The decided sequence is: verify the confirmed hash, create the sandbox, execute as written and in order, exit the sandbox, synchronize the authorized result back to main, and finish. The proposal for failure handling is to extract partial output, exit without synchronization, and return to Planner; this remains a proposal until accepted.

## 5. Rules applied in every stage

### Authority

| Claim | Authority |
|---|---|
| User intent | User's current explicit decision |
| Existing implementation | Physical source and runtime evidence |
| Historical intent | Git history and accepted project records |
| External behavior | Official documentation and official source repositories |
| General guidance | Trusted primary sources |

Reference sources teach patterns only. They do not authorize copying their architecture, files, dependencies, examples, or assumptions. When evidence is incomplete, record Known, Unknown, and Source Needed.

### Reuse before rebuild

For a requirement that references a standard-library module, installed package, SDK, framework, or external codebase:

1. Check that the capability is importable and supports the required behavior.
2. Import and use it; do not copy, reproduce, rebuild, vendor, or reimplement it.
3. A thin adapter is allowed only for input mapping, output normalization, configuration, or error translation.
4. If it cannot be imported or does not cover the requirement, record the evidence and classify it as `uncertainty`, `partial`, or `not_covered`.
5. A custom implementation needs an explicit Planning decision in the Decision Log explaining why reuse is insufficient.

A reference is evidence to evaluate for reuse, never authorization to recreate it.

### Evidence limits

Never invent files, folders, APIs, signatures, schemas, dependencies, versions, counts, results, runtime behavior, tests, fixtures, or architecture. No completion claim exceeds executed evidence. One verified slice is not the whole product. Fixtures, mocks, simulations, reports, manifests, and sandbox artifacts do not prove live behavior. Show a fixture only when a real fixture exists or repeatable behavior needs one, with path, filename, trigger, expected state, observable output, assertion, failure condition, and provenance.

Validation tests the user's intent: intent, method, expected result, observed result, and remaining gap.

### Proposal review and challenge

Planner reviews code proposals against outcome/task completion, reliability, groundedness/policy adherence, and cost/speed. Each proposal carries a Verification section with setup, lint, test, and build commands filled from the repository. Commands must be verified before use. Cost and speed are information, not authority to weaken evidence or authorization.

A finding states the issue, evidence, reference source, and effect on user intent. A correction draft states the smallest correction, behavior to preserve, verification required, and work that must not be introduced. When no correction is needed, no correction plan is written.

A challenge names the finding, evidence, and effect on user intent. The receiving agent may answer with contrary repository evidence, a missing constraint, or a smaller correction. Evidence settles disagreement, not confidence. Challenge-round limits remain open.

## 6. Records and reports

Planner keeps every record. Other agents provide evidence and do not edit an approved definition.

### Living ExecPlan

Keep one `PLANS.md` ExecPlan. Its four required sections are Progress; Surprises & Discoveries with evidence snippets; Decision Log; and Outcomes & Retrospective.

### Feature status

`feature_list.json` is the approved definition. Tests are never removed, edited, reordered, or combined. Features with a UI are verified in the actual UI through a real browser: click, type, scroll, capture a screenshot at each step, and inspect console errors. Curl-only testing and JavaScript shortcuts do not count for UI verification.

The proposed mutable status values are `not_run`, `completed`, `failed`, `blocked`, and `skipped`; status is excluded from the approval digest. Only the Auditor's valid verdict sets `completed`, written by Runtime once evidence files exist and are hashed. A feature declares a verification surface (`ui`, `api`, `cli`, or `library`); the browser rule applies to `ui`.

### Progress, handoff, and missing context

The progress file is named `work-progress`, set once in configuration. Counts are computed from feature statuses, never hand-written.

The handoff uses one shared shape: `agent`, `status`, `input_refs`, `output_refs`, `resume_at`, and `questions`. Artifact identifiers/digests, request id, attempt, and the final status vocabulary require the decisions recorded in the open-decision list below.

`missing_context` records a target identifier and reason for a referenced file or symbol that the input did not include, and why it is needed. The proposed schema requires the field (empty list means checked and none missing), rejects extra keys and empty strings, and records id, kind (`file` or `symbol`), `referenced_from`, and `blocks`. Runtime checks each entry against the supplied manifest and repository. Cross-agent Pydantic schemas live in `shared/models.py`; the SDK strips some constraints, so Pydantic re-validates every response.

### Stage report

Every stage reports date/time, title, source target, completed/total progress, readiness (`valid`, `uncertainty` with unsupported part, or `blocked` with exact blocker), gaps, updates, remaining work, action performed, exact commands and outputs, code details when applicable, and real unresolved issues. When work remains, report the current issue, last action, and handoff recommendation. Detail sections may be collapsed; corrected work and observable success criteria remain visible.

## 7. Package layout

The package layout is the target. It preserves a single application entry point and local ownership of agent and subsystem tests.

```text
breakdown/
├── __init__.py
├── __main__.py                  # only entry point; builds the agents dict
├── tests/                       # layering, cross-agent contracts, workflow-level
├── shared/                      # imports nothing above itself
│   ├── __init__.py
│   ├── base.py
│   ├── models.py
│   ├── config.py
│   └── tests/
├── agents/
│   ├── __init__.py              # explicit imports; no import-time construction
│   ├── loop.py                  # shared model loop
│   ├── prompt.py
│   ├── researcher/
│   │   ├── __init__.py
│   │   ├── agent.py             # YAML module docstring + Python implementation
│   │   └── tests/
│   ├── auditor/
│   │   ├── __init__.py
│   │   ├── agent.py             # YAML module docstring + Python implementation
│   │   ├── coder.py             # Auditor-owned read-only capability
│   │   └── tests/
│   ├── planner/
│   │   ├── __init__.py
│   │   ├── agent.py             # YAML module docstring + Python implementation
│   │   └── tests/
│   └── builder/
│       ├── __init__.py
│       ├── agent.py             # YAML module docstring + Python implementation
│       └── tests/
└── system/
    ├── runtime/
    │   ├── __init__.py
    │   └── sandbox.py
    ├── storage/
    ├── tools/
    ├── safety.py
    ├── memory.py
    └── tests/
```

Decided boundaries: `shared/` is a sibling of `agents/` and `system/`; there is one `__main__.py` at `breakdown/`; each agent folder owns its `agent.py` and tests; Coder is inside Auditor; no separate `host/` or `contracts/` directory is introduced in this layout discussion.

### YAML agent definition in Python

Each agent's `agent.py` starts with a YAML module docstring, followed by ordinary Python implementation. The docstring must be the first module statement, before `from __future__ import annotations`, so AST discovery cannot silently lose it when imports are reordered.

The YAML definition describes agent identity, purpose, instructions, input-contract name, and response-contract name. The Python implementation defines behavior. The YAML is parsed with a safe loader that rejects duplicate keys, then validated against a strict Pydantic definition schema. The agent id must match its containing folder. Contract references must resolve to the intended classes in `shared/models.py` and satisfy the shared strict-model rule. Definition discovery uses AST and does not import or execute the implementation module.

The YAML instructions are the canonical agent instructions. Do not keep a separately hand-maintained `SKILL.md` or duplicate the same instructions in another prompt constant. A generated view is allowed only when a consumer demonstrably requires it.

Definition metadata does not authorize execution. Runtime owns dispatch, approval checks, permissions, workflow transitions, and enforcement. Importing an agent module must not instantiate agents, read credentials, open Storage, or perform external work. `__main__.py` constructs the four agents and injects them into Runtime.

### Dependency direction

- `shared/` imports nothing from `agents/` or `system/`.
- `system/` never imports `agents/`.
- Agents import `shared/` and authorized `system/` capabilities, but do not import sibling agents.
- `__main__.py` is the composition root and hands the constructed agents to Runtime.
- Agent instances are created at application construction, not at import time.

## 8. Evidence and migration limits

The November 24 layout probes and the November 25 YAML-docstring prototype were performed on stubs/prototypes. They do not prove the target layout works against the current repository, live models, sandbox, Strands, browser UI, or live structured-output requests. The actual repository migration must preserve current behavior and persistence, then run source-backed checks before legacy paths are removed.

## 9. Open decisions

The following remain open unless a later accepted Decision Log entry resolves them:

1. Whether Builder calls the model directly or runs only the exact steps in the plan.
2. Whether Builder stops at the first failed task or continues independent tasks.
3. Whether a corrected to-do within the same approved scope requires new confirmation.
4. Correction-loop and challenge-round caps.
5. Whether existing Markdown research/plan files carry into the rebuild alongside JSON records.
6. Whether `memory.py` owns run records or model context (persistence remains under the single Storage owner).
7. Jobs for `coding.py` and `openai_compatible.py`; keep them out until justified by source.
8. Test directory convention (`tests/` versus `test/`); target currently uses `tests/`.
9. Exact location and interface for the independent `verify_all()` operation.
10. Final shared handoff shape, including artifact provenance fields.
11. The code migration's final target branch and merge procedure.
