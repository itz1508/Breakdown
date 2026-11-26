# Workflow Target

This document records the target workflow and its authority boundaries. It is not a command sequence for an agent to execute outside Runtime.

## Flow

| Step | Owner | Work |
|---:|---|---|
| 1 | Runtime | Start or resume the session and preserve the user's input. |
| 2 | Auditor | Prepare a revisioned specification in `discovery.json`. |
| 3 | User + Runtime | Review the streamed edit preview. Preserve every revision, including agent edits and manual changes. |
| 4 | User + Auditor + Runtime | Decline and retain without Build, or Accept & Check the exact revision. A material issue returns to clarification; changed content requires another review and acceptance. |
| 5 | Researcher | Investigate accepted research items only; preserve source provenance, contradictions and unknowns. |
| 6 | Auditor | Compare research findings with repository evidence and identify gaps or contradictions. |
| 7 | Planner | Create the project/phase/task decomposition, define task To-dos, resolve gaps and prepare the exact package. |
| 8 | User + Runtime | Confirm the exact package revision and source checkpoint. |
| 9 | Builder + Runtime | Verify the binding, execute the confirmed work in the authorized sandbox, export the result and exit. |
| 10 | Independent verifier + Runtime | Validate the exported result independently, then retain completion evidence and outcome. |

## Work decomposition

The project work tree is Project → Phases → Tasks → To-do. A Task is a cohesive, independently verifiable unit. Its To-do contains a small number of guidance steps, generally one to three. It is not a batch, wave, scheduler, or deferred execution queue.

Task dependencies determine ordering. Independent tasks may run concurrently when the host authorizes that execution. Builder follows the confirmed task order and cannot add, remove, reorder or skip tasks.

## Approval and invalidation

Acceptance binds the exact specification revision. Package confirmation binds the exact package revision and source checkpoint. Any content change invalidates the corresponding approval binding. A corrected package requires a new digest and new user confirmation.

## Verification and retention

Builder's own report is not independent validation. The verifier evaluates exported results using evidence external to Builder's self-report. Runtime records validation evidence and the completion/retention outcome. Any check not actually executed is recorded as not run; uncertainty is not converted into a valid result.
