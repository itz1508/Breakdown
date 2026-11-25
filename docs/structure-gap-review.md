# Structure Gap Review — Latest Four-Agent Target

**Date:** 2026-11-25  
**Target branch:** `migration/latest-four-agent-layout`  
**Baseline:** `main` at `71218fe820208ff3b5e6118ea5c017568f7a5a73`  
**Pre-review branch head:** `268344f98bc73878a764a37099442059eb3859b1`  
**Scope:** target structure, workflow alignment, documentation consistency, source-owner map, and stale-path removal safety. This is not a claim that the Python migration or runtime tests have completed.

## Executive result

The initial PR correctly stated the four-agent target but had gaps that could misdirect implementation. The target document now distinguishes accepted decisions from proposals, assumptions, and open decisions; the migration plan now separates file relocation from the actual workflow/schema replacement and identifies the authorization and TaskTodo ownership boundaries.

No production Python files, tests, executable configuration, or legacy paths were changed by this gap-fix pass. The current runtime remains on the original eight-stage `breakdown.yaml` with root `agents/skills/*.md` guidance and the flat `breakdown/roles/` implementation. Those paths are still live dependencies and cannot be deleted safely yet.

## Findings and fixes

| ID | Severity | Gap found | Correction |
|---|---|---|---|
| G-01 | High | `PLANS.md` had a `Current Architecture and Workflow Record` section presenting the old five-role architecture as active and saying Coder-under-Auditor was superseded. | Replaced the stale current-design section with the latest four-agent target and corrected feature-list/browser-verification wording. |
| G-02 | High | The migration objective implied that the entire latest workflow could be obtained by behavior-preserving file moves. Current source is an eight-stage workflow; the target has specification revision/Accept & Check, accepted-item research, Auditor comparison, TaskTodo planning, exact package confirmation, Builder export/exit, independent validation, and retention. | Split pure package relocation from explicit workflow/state/schema replacement. The old runtime remains active until the new model, transitions, gates, and persistence are wired and tested. |
| G-03 | High | The source-owner map put all of `breakdown/roles/__init__.py` into `agents/loop.py`. That file includes `RoleToolkit` capability grants and dispatch, not only prompt/structured-output helpers. | Split pure loop/render/structured-output helpers into `agents/loop.py`; place RoleToolkit, grants, and dispatch on the System tools boundary. |
| G-04 | High | The target lacked the agreed shared `TaskTodo` work representation and did not call out the current `BuildTask`/ImplementationPlan conversion. | Added `shared/queue/TaskTodo` as the shared representation and made BuildTask-to-TaskTodo an explicit schema/behavior conversion. No scheduler, deferred queue, wave, or batch abstraction is authorized. |
| G-05 | High | YAML definition validation was underspecified and contract resolution was restricted to `shared/models.py`, excluding agent-private contracts. | Specified a duplicate-key-rejecting SafeLoader, strict Pydantic definition validation (`extra="forbid", strict=True`), folder/id matching, AST-only resolution, and strict-base inheritance. Agent-private contracts may live in the owning `agent.py`; cross-agent contracts belong in `shared/models.py`. |
| G-06 | Medium | Proposed Researcher decomposition, feature-status behavior, count derivation, handoff extensions, and dependency rules were worded as accepted. | Marked proposals, the `role` → `agent` assumption, handoff-under-review status, and open decisions explicitly. |
| G-07 | Medium | The illustrative tree used `tests/` while the test directory naming decision remained open. | Marked `tests/` as illustrative/provisional and preserved the open decision. |
| G-08 | Medium | The migration plan assigned `system/memory.py` a settled semantic role despite the open question of run records versus model context. | Kept the proposed path but marked semantics open; prohibited creating a second run store. |
| G-09 | High | Current `breakdown.yaml` still references five top-level `agents/skills/*.md` files, including Coder. Blindly changing/removing these references would break the active workflow. | Documented the live dependency and gated role-guidance replacement on new YAML definitions, Runtime discovery, and repointing all consumers. Old files remain untouched. |
| G-10 | Medium | Current protected-path logic reflects the top-level package layout; moving application code under `breakdown/agents`, `breakdown/shared`, and `breakdown/system` may leave those paths outside existing protection checks. | Added a required safety/protected-path reconciliation before legacy removal. |
| G-11 | Medium | The test relocation plan did not inventory the baseline tests or explain how to preserve assertions. | Added the current test filename inventory and required intact test-case moves, with no edits, deletions, reordering, or combining. |
| G-12 | Medium | Architecture documentation said the target independent Coder role was not implemented, which contradicted current Auditor-owned Coder behavior. | Corrected the wording: Coder already exists as an Auditor-injected read-only capability; the target preserves that ownership. |
| G-13 | Medium | The legacy cleanup phases did not clearly make workflow migration a prerequisite for retiring the old executable config. | Added a distinct workflow/state migration phase before repository consumer rewiring and legacy removal. |

## Remaining source-level blockers

These are not documentation defects and were not marked completed:

1. The four agent folders and YAML-docstring definitions do not yet exist in the runtime package.
2. Current `breakdown.yaml` still uses eight stages and old `agents/skills/*.md` role-guidance references.
3. Runtime, stores, safety, tools, and imports remain in the current flat package.
4. Root tests and their fixtures have not been relocated.
5. Static AST discovery, duplicate-key rejection, Pydantic strict definition validation, agent-id/folder matching, and contract-reference verification are not yet implemented against the real package.
6. Workflow state/approval/artifact conversion and BuildTask-to-TaskTodo have not been implemented.
7. The target's dependency rule remains a proposal until accepted and then enforced by layering tests.
8. Builder policy, handoff, loop caps, memory semantics, test-directory spelling, and independent `verify_all()` interface remain open where shown in the target document.

## Verification performed

- Inspected the GitHub recursive tree and confirmed the existing source layout, root test inventory, top-level skill files, and current workflow/config references.
- Re-read the target architecture, migration map, PLANS.md, current architecture docs, and the historical Researcher ExecPlan.
- Compared current target decisions with the November 24 workflow/layout source and the YAML-docstring prototype findings.
- No runtime commands or test suite were run: this pass changes design/migration documentation only.
- No live model, sandbox, Strands, browser UI, or production repository execution was performed.

## Consolidation rule

A stale file is not removable merely because its replacement path is described. First implement the replacement owner, repoint every runtime/test/eval/script/config/docs consumer, prove the relevant behavior, and only then delete the old file. When ownership or behavior is uncertain, leave the old path intact and record the missing evidence.
