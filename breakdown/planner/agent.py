"""Planner role: owns the authoritative ImplementationPlan.

Stage: implementation_planning. The Planner creates the single
authoritative plan with cohesive ordered BuildTasks, approved target
paths, capability reuse decisions, expected results, and validation. It
never freezes, approves, executes, or synchronizes the plan — those are
deterministic runtime operations.
"""

from __future__ import annotations

from breakdown.shared.base import RoleOperationError
from breakdown.shared.model_loop import generate_structured, load_skill_prompt, render_json
from breakdown.shared.models import (
    ImplementationPlanningInput,
    ImplementationPlanningOutput,
    RoleBackend,
    RoleBackendRequest,
    StageContext,
)
from breakdown.system.tools.toolkit import RoleToolkit

_PLANNER_BRIEF = load_skill_prompt(__file__)


class Planner:
    def __init__(self, *, backend: RoleBackend, tools: RoleToolkit) -> None:
        self._backend = backend
        self._tools = tools

    async def create_implementation_plan(
        self, input_value: ImplementationPlanningInput, context: StageContext
    ) -> ImplementationPlanningOutput:
        findings = [finding.model_dump(mode="json") for finding in input_value.classified_findings]
        normalized_evidence = [
            evidence.model_dump(mode="json") for evidence in input_value.normalized_evidence
        ]
        fixtures = [
            fixture.model_dump(mode="json") for fixture in input_value.reviewed_fixture_specifications
        ]
        unresolved = [question.model_dump(mode="json") for question in input_value.reviewed_unresolved_questions]
        processing_plan = input_value.processing_plan.model_dump(mode="json")
        checkpoint_context = {
            "repository_identity": input_value.source_checkpoint.repository_identity,
            "commit_sha": input_value.source_checkpoint.commit_sha,
            "captured_at": input_value.source_checkpoint.captured_at.isoformat(),
            "tracked_file_count": len(input_value.source_checkpoint.file_hashes),
            "untracked_file_count": len(input_value.source_checkpoint.untracked_file_hashes),
        }
        prompt = (
            "Create one ImplementationPlan from the accepted intent and reviewed evidence.\n"
            f"Exact user intent:\n{input_value.exact_user_intent}\n\n"
            f"Planning processing plan:\n{render_json(processing_plan)}\n\n"
            f"Classified findings:\n{render_json(findings)}\n\n"
            f"Normalized evidence and provenance:\n{render_json(normalized_evidence)}\n\n"
            f"Reviewed fixture specifications:\n{render_json(fixtures)}\n\n"
            f"Reviewed unresolved questions:\n{render_json(unresolved)}\n\n"
            f"Source checkpoint context:\n{render_json(checkpoint_context)}\n\n"
            "Analyze requirement coverage, existing capability reuse, interface and dependency "
            "compatibility, target-path ownership, security, fixtures, and verification coverage. "
            "Resolve only planning-owned gaps. Preserve unresolved questions, map every task to "
            "reviewed requirement/evidence, and produce cohesive independently verifiable tasks "
            "with target paths, expected outcomes, and validation steps. Do not invent evidence."
        )
        request = RoleBackendRequest(
            operation="create_implementation_plan",
            system_prompt=_PLANNER_BRIEF,
            prompt=prompt,
            output_schema=ImplementationPlanningOutput.model_json_schema(),
            tool_names=self._tools.allowed_names(),
        )
        output = await generate_structured(self, self._backend, request, ImplementationPlanningOutput)
        _validate_trace(output, input_value)
        return output


def _validate_trace(output: ImplementationPlanningOutput, input_value: ImplementationPlanningInput) -> None:
    plan = output.implementation_plan
    declared = set(plan.requirement_refs)
    for task in plan.tasks:
        unknown = set(task.requirement_refs) - declared
        if unknown:
            raise RoleOperationError(
                f"task {task.task_id} references requirements missing from the plan trace: {sorted(unknown)}"
            )
    finding_refs = {finding.requirement_ref for finding in input_value.classified_findings}
    untraced = finding_refs - declared
    if untraced:
        raise RoleOperationError(f"requirement trace incomplete; missing: {sorted(untraced)}")
    unsupported = declared - finding_refs
    if unsupported:
        raise RoleOperationError(
            f"plan references requirements without reviewed findings: {sorted(unsupported)}"
        )
