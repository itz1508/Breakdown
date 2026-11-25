# Workflow and Data Flow

This page describes the executable eight-stage workflow in breakdown.yaml.

## Stage map

| Order | Stage | Owner | Operation / result |
|---:|---|---|---|
| 1 | research_proposal | Auditor | Preserves user intent, classifies candidate requirements and capability coverage, identifies research questions and creates the Research processing plan |
| 2 | research_approval | User | Records approve or cancellation against the proposal, processing plan and source checkpoint |
| 3 | research_execution | Researcher | Answers approved questions with evidence, contradictions, limitations and unresolved questions |
| 4 | findings_review | Auditor | Classifies research findings, normalizes evidence and reviews fixture specifications and unresolved questions |
| 5 | implementation_planning | Planner plus deterministic runtime steps | Produces the implementation plan, freezes it, hashes it and runs preflight |
| 6 | plan_approval | User | Approves, requests changes, or declines the exact frozen plan and source checkpoint |
| 7 | build_execution | Builder plus safety boundary | Executes in sandbox, records task/check results, independently detects changes and conditionally synchronizes approved paths |
| 8 | completion | Deterministic runtime | Validates terminal outcome and records completion/report data |

The exact stage contracts and artifact keys are declared in breakdown.yaml. Stage operation models and output mappings are in breakdown/models.py and breakdown/contracts.py.

## Approval and transition flow

~~~mermaid
flowchart TD
    A[Initial request] --> B[1 Auditor: research_proposal]
    B --> C{2 User: research_approval}
    C -->|approve| D[3 Researcher: research_execution]
    C -->|cancel or timeout| Z[8 Completion]
    D --> E[4 Auditor: findings_review]
    E --> F[5 Planner: implementation_planning]
    F --> G{6 User: plan_approval}
    G -->|approve| H[7 Builder: build_execution]
    G -->|request_changes| F
    G -->|decline, timeout or loop exhausted| Z
    H --> Z
~~~

Plan-approval changes return to planning with a bounded loop. The YAML declares a maximum of three plan-approval change loops. A newly required path or plan contradiction discovered during Build has its own bounded return to implementation_planning; synchronization is prohibited for that attempt and renewed approval is required.

## Processing plans and implementation plan

A ProcessingPlan is authored for the next cross-role handoff. The workflow definition requires one processing plan per cross-role handoff, with the destination stage, input refs, expected output keys, completion criteria and evidence requirements validated by Runtime.

The Planner's ImplementationPlan is the canonical implementation specification. Its tasks are cohesive, sequential, independently verifiable changes with target paths, expected results and validation steps. Runtime freezes and hashes the plan before presenting the approval decision.

## Core artifacts

Artifact keys are logical identifiers, not physical paths. Runtime owns physical path assignment according to storage policy. JSON records are authoritative; Markdown reports are projections that reference their JSON source.

Important artifact families include:

- Initial request, Research proposal, processing plans and Research records.
- Findings review, normalized evidence, unresolved questions and reviewed fixtures.
- ImplementationPlan, frozen plan, frozen plan hash and preflight result.
- Builder task results, applied changes, validation results and execution evidence.
- Source checkpoints, synchronization result, resulting checkpoint and completion record.

Use the models and workflow definition to discover the exact current field shape. This page intentionally does not duplicate the full Pydantic schemas.

## Evidence and freshness

Each artifact reference carries an artifact key, revision and digest. Reads verify the digest. The run pins the workflow ID, definition version and digest. The source checkpoint records repository identity, commit identity where available, tracked file digests and relevant untracked file digests.

If approved plan inputs change, downstream results are invalidated according to the declared loop-back rules. Historical artifacts remain available; the runtime must not consume stale results as current.

## Completion

Completion is deterministic and evidence-bounded. A successful outcome requires the completion accepts-matrix and synchronization/validation conditions in the workflow definition and runtime to be satisfied. Missing, failed, skipped, uncertain, or budget-exhausted work must not be promoted to success.

For CLI walkthroughs and recovery commands, see [Operations](operations.md).
