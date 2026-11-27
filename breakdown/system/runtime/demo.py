"""Offline demo backends (D26): scripted, schema-valid outputs so the full
eight-stage workflow can be exercised without any model SDK.

The demo scenario is self-contained: one requirement (create
``DEMO_CHANGE.md`` in the target), one research question, one build task.
Demo outputs are clearly labeled; the demo coding backend writes the file
inside the sandbox and the safety boundary synchronizes it like any real
build result.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from breakdown.shared.models import (
    CodingBackendResult,
    ExecutionResult,
    RoleBackendResponse,
    TokenUsage,
)


class DemoBackendError(RuntimeError):
    """The offline demo backend received an operation it does not script."""


def _plan_dict(objective: str, input_refs: list[str], output_keys: list[str]) -> dict[str, Any]:
    return {
        "objective": objective,
        "input_refs": input_refs,
        "steps": ["follow the approved processing plan"],
        "expected_output_keys": output_keys,
        "completion_criteria": ["every declared output produced"],
        "evidence_required": ["provenance for material claims"],
    }


def demo_role_outputs(request_text: str) -> dict[str, dict[str, Any]]:
    """Canned, validator-passing outputs for the four role operations."""
    intent = request_text.strip() or "Demonstrate the OneShot Breakdown workflow"
    proposal = {
        "exact_user_intent": intent,
        "candidate_requirements": [
            {
                "requirement_id": "demo-req-1",
                "text": "Create DEMO_CHANGE.md recording the demonstrated change",
                "origin": "user",
                "coverage": "not_covered",
                "evidence": "DEMO_CHANGE.md does not exist in the target",
            }
        ],
        "research_questions": [
            {
                "question_id": "demo-q-1",
                "text": "What should the demo change record contain?",
                "reason": "scope",
            }
        ],
        "candidate_source_responsibilities": [
            {"requirement_refs": ["demo-req-1"], "purpose": "record the demonstrated change", "path": "DEMO_CHANGE.md"}
        ],
        "research_execution_processing_plan": _plan_dict(
            "Answer the approved demo question", ["research_proposal"], ["research_response"]
        ),
    }
    research = {
        "research_record": {
            "record_id": "demo-rr-1",
            "resolved_questions": [
                {
                    "question_id": "demo-q-1",
                    "answer": "A short Markdown note quoting the request text",
                    "evidence_refs": ["demo-ev-1"],
                }
            ],
            "unresolved_questions": [],
            "evidence": [
                {
                    "evidence_id": "demo-ev-1",
                    "claim": "demo answer derived from the request",
                    "source_identity": "offline-demo",
                    "source_location": "demo",
                    "accessed_at": "2026-01-01T00:00:00+00:00",
                    "status": "supported",
                }
            ],
            "contradictions": [],
            "fixture_specifications": [],
        },
        "report_summary": "demo question resolved",
        "research_todo": {"items": [{"question_id": "demo-q-1", "status": "completed"}]},
    }
    return _finish_demo_outputs(proposal, research)


def _finish_demo_outputs(proposal: dict[str, Any], research: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = {
        "classified_findings": [
            {
                "finding_id": "demo-f-1",
                "requirement_ref": "demo-req-1",
                "claim": "DEMO_CHANGE.md is missing from the target",
                "status": "supported",
                "decision_trace": [{"check": "inspected target", "observation": "true", "evidence_ref": "demo-ev-1"}],
                "criterion": "valid",
                "reason": "direct observation",
            }
        ],
        "normalized_evidence": [],
        "reviewed_fixture_specifications": [],
        "reviewed_unresolved_questions": [],
        "contradictions_preserved": [],
        "implementation_planning_processing_plan": _plan_dict(
            "Create the demo ImplementationPlan", ["findings_review"], ["implementation_plan"]
        ),
    }
    plan = {
        "planning_gap_analysis": ["demo file missing"],
        "planning_gap_resolutions": ["create DEMO_CHANGE.md"],
        "implementation_plan": {
            "plan_id": "demo-plan-1",
            "revision": 1,
            "objective": "Create DEMO_CHANGE.md",
            "requirement_refs": ["demo-req-1"],
            "source_checkpoint_ref": {"artifact_key": "source_checkpoint", "digest": "1" * 64},
            "technology_decisions": [],
            "tasks": [
                {
                    "task_id": "demo-task-1",
                    "sequence": 1,
                    "responsibility": "create the demo change record",
                    "requirement_refs": ["demo-req-1"],
                    "target_paths": [{"path": "DEMO_CHANGE.md", "disposition": "create"}],
                    "source_evidence": ["demo-ev-1"],
                    "capability_reuse": [],
                    "reference_ids": [],
                    "expected_result": "DEMO_CHANGE.md contains the request text provided to this run",
                    "validation_steps": [
                        {
                            "step_id": "demo-v-1",
                            "description": "file exists",
                            "command_or_observation": "read DEMO_CHANGE.md",
                            "expected": "present",
                        }
                    ],
                    "required_evidence": ["file content"],
                }
            ],
            "integration_checks": [],
            "success_criteria": [{"criterion": "demo file created", "measurable": True}],
        },
        "planning_review_result": {"cohesion": "valid", "notes": ""},
        "build_execution_processing_plan": _plan_dict(
            "Execute the approved demo task in the sandbox", ["implementation_plan"], ["task_results"]
        ),
    }
    return {
        "create_research_proposal": proposal,
        "execute_research": research,
        "review_research_findings": findings,
        "create_implementation_plan": plan,
    }


class OfflineDemoRoleBackend:
    """Scripted role backend plus deterministic, fixture-only demo verification."""

    def __init__(self, request_text: str) -> None:
        self._outputs = demo_role_outputs(request_text)
        self._request_text = request_text.strip() or "Demonstrate the OneShot Breakdown workflow"

    async def generate(self, request: Any) -> RoleBackendResponse:
        if request.operation == "verify_build_task":
            start_tag = "<verification_input_json>"
            end_tag = "</verification_input_json>"
            try:
                start = request.prompt.index(start_tag) + len(start_tag)
                end = request.prompt.index(end_tag, start)
                verification_input = BuildVerificationInput.model_validate(
                    json.loads(request.prompt[start:end].strip())
                )
            except (ValueError, json.JSONDecodeError) as exc:
                raise DemoBackendError(
                    "offline demo verifier received invalid verification input"
                ) from exc

            verdicts: list[dict[str, str]] = []
            for task in verification_input.tasks:
                command_steps = [
                    step.step_id for step in task.validation_steps if step.kind == "command"
                ]
                observed = [
                    file for file in task.observed_files
                    if file.status == "read" and not file.truncated
                ]
                has_request_text = any(
                    file.path == "DEMO_CHANGE.md" and self._request_text in file.content
                    for file in observed
                )
                if command_steps:
                    criterion = CriterionResult.UNCERTAINTY
                    observation = (
                        f"offline demo cannot execute command steps: {sorted(command_steps)}"
                    )
                elif has_request_text:
                    criterion = CriterionResult.VALID
                    observation = "Host observed the exact request text in the sandbox file."
                else:
                    criterion = CriterionResult.NOT_VALID
                    observation = (
                        "Host did not observe the exact request text in a readable sandbox file."
                    )
                verdicts.append(
                    {
                        "check_ref": task.task_ref,
                        "criterion": criterion.value,
                        "expected": task.expected_result,
                        "actual_observation": observation,
                    }
                )
            payload: Mapping[str, Any] = {"task_verifications": verdicts}
        else:
            payload = self._outputs.get(request.operation)
        if payload is None:
            raise DemoBackendError(
                f"offline demo backend has no scripted output for {request.operation}"
            )
        return RoleBackendResponse(
            structured_output=dict(payload),
            text="",
            usage=TokenUsage(input_tokens=50, output_tokens=50, tool_calls=1),
            provider="offline-demo",
            model="offline-demo",
        )


class OfflineDemoCodingBackend:
    """Scripted coding backend: creates DEMO_CHANGE.md inside the sandbox."""

    def __init__(self, request_text: str) -> None:
        self._text = request_text.strip() or "Demonstrate the OneShot Breakdown workflow"

    async def apply_task(self, request: Any) -> CodingBackendResult:
        sandbox = Path(request.sandbox_root)
        (sandbox / "DEMO_CHANGE.md").write_text(f"# Demo change\n\nRequest: {self._text}\n", encoding="utf-8")
        return CodingBackendResult(
            execution_result=ExecutionResult.COMPLETED,
            observation="DEMO_CHANGE.md created in sandbox",
            reported_changed_paths=("DEMO_CHANGE.md",),
            usage=TokenUsage(input_tokens=25, output_tokens=25, tool_calls=1),
        )
