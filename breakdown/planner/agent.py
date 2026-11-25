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
from breakdown.shared.models import RoleBackend
from breakdown.shared.models import (
    ImplementationPlanningInput,
    ImplementationPlanningOutput,
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
        unresolved = [question.model_dump(mode="json") for question in input_value.reviewed_unresolved_questions]
        prompt = (
            "Create the ImplementationPlan for this request.\n"
            f"Exact user intent:\n{input_value.exact_user_intent}\n\n"
            f"Classified findings:\n{render_json(findings)}\n\n"
            f"Unresolved questions:\n{render_json(unresolved)}\n\n"
            "Analyze planning gaps, resolve the ones Planning owns, and produce "
            "ordered cohesive BuildTasks with target paths, reuse decisions, "
            "expected results, and validation steps."
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
