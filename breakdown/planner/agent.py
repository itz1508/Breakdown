"""Planner role: owns the authoritative ImplementationPlan.

Stage: implementation_planning. The Planner creates the single
authoritative plan with cohesive ordered BuildTasks, approved target
paths, capability reuse decisions, expected results, and validation. It
never freezes, approves, executes, or synchronizes the plan — those are
deterministic runtime operations.
"""

from __future__ import annotations

from pathlib import Path
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
        _run_planning_gap_scan(output, input_value, self._tools.root)
        return output


def _run_planning_gap_scan(
    output: ImplementationPlanningOutput,
    input_value: ImplementationPlanningInput,
    repository_root: Path,
) -> None:
    """Run bounded deterministic consistency checks over Planner's draft plan."""
    plan = output.implementation_plan
    gaps: list[str] = []

    declared_requirements = set(plan.requirement_refs)
    if len(plan.requirement_refs) != len(declared_requirements):
        gaps.append("implementation plan contains duplicate requirement references")

    finding_requirement_refs = {
        finding.requirement_ref for finding in input_value.classified_findings
    }
    missing_requirements = finding_requirement_refs - declared_requirements
    unsupported_requirements = declared_requirements - finding_requirement_refs
    if missing_requirements:
        gaps.append(f"requirements without plan coverage: {sorted(missing_requirements)}")
    if unsupported_requirements:
        gaps.append(f"plan requirements without reviewed findings: {sorted(unsupported_requirements)}")

    finding_ids = {finding.finding_id for finding in input_value.classified_findings}
    evidence_ids = {
        step.evidence_ref
        for finding in input_value.classified_findings
        for step in finding.decision_trace
        if step.evidence_ref
    }
    evidence_ids.update(item.evidence_ref for item in input_value.normalized_evidence)
    known_source_refs = finding_ids | evidence_ids

    for decision in plan.technology_decisions:
        unknown_refs = set(decision.evidence_refs) - known_source_refs
        if unknown_refs:
            gaps.append(
                f"technology decision {decision.topic!r} references unknown evidence: "
                f"{sorted(unknown_refs)}"
            )

    fixture_ids = {
        fixture.fixture_id for fixture in input_value.reviewed_fixture_specifications
    }
    if len(plan.fixture_refs) != len(set(plan.fixture_refs)):
        gaps.append("implementation plan contains duplicate fixture references")
    unknown_fixtures = set(plan.fixture_refs) - fixture_ids
    if unknown_fixtures:
        gaps.append(f"plan references fixtures not reviewed by Auditor: {sorted(unknown_fixtures)}")

    if output.planning_review_result.cohesion is not CriterionResult.VALID:
        gaps.append(
            f"Planner cohesion assessment is {output.planning_review_result.cohesion.value}"
        )

    task_by_id = {task.task_id: task for task in plan.tasks}
    sequence_by_id = {task.task_id: task.sequence for task in plan.tasks}
    root = repository_root.resolve()
    for task in plan.tasks:
        task_requirements = set(task.requirement_refs)
        unknown_requirements = task_requirements - declared_requirements
        if unknown_requirements:
            gaps.append(
                f"task {task.task_id!r} references undeclared requirements: "
                f"{sorted(unknown_requirements)}"
            )
        if len(task.requirement_refs) != len(task_requirements):
            gaps.append(f"task {task.task_id!r} contains duplicate requirement references")

        task_sources = set(task.source_evidence)
        if not task_sources:
            gaps.append(f"task {task.task_id!r} has no source evidence references")
        unknown_sources = task_sources - known_source_refs
        if unknown_sources:
            gaps.append(
                f"task {task.task_id!r} references unknown source evidence: {sorted(unknown_sources)}"
            )
        duplicate_targets = [
            path for path in {target.path for target in task.target_paths}
            if sum(target.path == path for target in task.target_paths) > 1
        ]
        if duplicate_targets:
            gaps.append(f"task {task.task_id!r} repeats target paths: {sorted(duplicate_targets)}")

        for target in task.target_paths:
            resolved = (root / target.path).resolve()
            if not resolved.is_relative_to(root):
                gaps.append(f"task {task.task_id!r} target escapes the repository: {target.path!r}")
                continue
            exists = resolved.exists()
            if target.disposition in {"modify", "delete"} and not resolved.is_file():
                gaps.append(
                    f"task {task.task_id!r} targets a missing/non-file path for "
                    f"{target.disposition}: {target.path!r}"
                )
            elif target.disposition == "create" and exists:
                gaps.append(
                    f"task {task.task_id!r} targets an existing path for create: {target.path!r}"
                )

        for dependency in task.depends_on:
            if dependency not in task_by_id:
                gaps.append(f"task {task.task_id!r} depends on unknown task {dependency!r}")
            elif sequence_by_id[dependency] >= task.sequence:
                gaps.append(
                    f"task {task.task_id!r} depends on task {dependency!r} that does not precede it"
                )

    if gaps:
        raise RoleOperationError("PlanningGapScan found material gaps: " + "; ".join(gaps))
