"""Deterministic planning runtime operations: freeze_plan + preflight_check.

Implements ``implementation_planning.runtime_steps`` from breakdown.yaml.
Pure deterministic functions — no model is ever invoked here. The
``PLANNING_OPERATIONS`` mapping adapts them to the deterministic-operation
registry consumed by the engine (P2-T7).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from breakdown.canonical import frozen_plan_hash as compute_frozen_plan_hash
from breakdown.checkpoint import checkpoint_is_fresh
from breakdown.contracts import DeterministicOperation
from breakdown.models import (
    CapabilityCoverage,
    CriterionResult,
    FrozenPlan,
    ImplementationPlan,
    PreflightCriterionRow,
    PreflightResult,
    SourceCheckpoint,
    StageContext,
    validate_target_path,
)


class PlanningOpsError(RuntimeError):
    pass


def freeze_plan(
    *,
    plan: ImplementationPlan,
    checkpoint: SourceCheckpoint,
    definition_version: int,
    frozen_at: datetime | None = None,
) -> FrozenPlan:
    return FrozenPlan(
        plan=plan,
        frozen_plan_hash=compute_frozen_plan_hash(plan, checkpoint, definition_version),
        source_checkpoint=checkpoint,
        definition_version=definition_version,
        frozen_at=frozen_at or datetime.now(UTC),
    )


def _row(name: str, criterion: CriterionResult, evidence: str = "") -> PreflightCriterionRow:
    return PreflightCriterionRow(name=name, criterion=criterion, evidence=evidence)


def check_source_checkpoint_freshness(checkpoint: SourceCheckpoint, target_root: Path) -> PreflightCriterionRow:
    fresh = checkpoint_is_fresh(checkpoint, target_root)
    return _row(
        "source_checkpoint_freshness",
        CriterionResult.VALID if fresh else CriterionResult.NOT_VALID,
        "checkpoint matches current repository state" if fresh else "repository drifted from the approved checkpoint",
    )


def check_plan_schema_valid(plan: ImplementationPlan) -> PreflightCriterionRow:
    try:
        ImplementationPlan.model_validate(plan.model_dump(mode="python"))
    except ValidationError as exc:
        return _row("implementation_plan_schema_valid", CriterionResult.NOT_VALID, str(exc)[:200])
    return _row("implementation_plan_schema_valid", CriterionResult.VALID, f"schema_version {plan.schema_version}")


def check_requirement_trace(plan: ImplementationPlan) -> PreflightCriterionRow:
    declared = set(plan.requirement_refs)
    if not declared:
        return _row("requirement_trace_complete", CriterionResult.NOT_VALID, "plan declares no requirement refs")
    for task in plan.tasks:
        unknown = set(task.requirement_refs) - declared
        if unknown:
            return _row(
                "requirement_trace_complete",
                CriterionResult.NOT_VALID,
                f"task {task.task_id} references untraced requirements: {sorted(unknown)}",
            )
    return _row("requirement_trace_complete", CriterionResult.VALID, "all task requirement refs trace to the plan")


def check_no_uncertainty_in_build_tasks(plan: ImplementationPlan) -> PreflightCriterionRow:
    problems: list[str] = []
    if plan.unresolved_items:
        problems.append(f"unresolved items present: {list(plan.unresolved_items)}")
    for task in plan.tasks:
        for reuse in task.capability_reuse:
            if reuse.coverage is CapabilityCoverage.UNCERTAINTY:
                problems.append(f"task {task.task_id}: uncertain capability {reuse.capability!r}")
    if problems:
        return _row("no_uncertainty_in_build_tasks", CriterionResult.NOT_VALID, "; ".join(problems))
    return _row("no_uncertainty_in_build_tasks", CriterionResult.VALID, "no uncertainty in build tasks")


def check_all_target_paths_mapped(plan: ImplementationPlan) -> PreflightCriterionRow:
    for task in plan.tasks:
        if not task.target_paths:
            return _row(
                "all_target_paths_mapped", CriterionResult.NOT_VALID, f"task {task.task_id} has no target paths"
            )
        for target in task.target_paths:
            try:
                validate_target_path(target.path)
            except ValueError as exc:
                return _row("all_target_paths_mapped", CriterionResult.NOT_VALID, str(exc))
    return _row("all_target_paths_mapped", CriterionResult.VALID, "every task maps at least one valid target path")


def check_target_dispositions_declared(plan: ImplementationPlan) -> PreflightCriterionRow:
    for task in plan.tasks:
        for target in task.target_paths:
            if not target.disposition:
                return _row(
                    "all_target_dispositions_declared",
                    CriterionResult.NOT_VALID,
                    f"task {task.task_id}: {target.path} has no disposition",
                )
    return _row("all_target_dispositions_declared", CriterionResult.VALID, "all dispositions declared")


def check_no_unapproved_path_overlap(plan: ImplementationPlan) -> PreflightCriterionRow:
    by_id = {task.task_id: task for task in plan.tasks}
    owners: dict[str, str] = {}
    for task in plan.tasks:
        for target in task.target_paths:
            owner_id = owners.get(target.path)
            if owner_id is not None and owner_id != task.task_id:
                owner_task = by_id[owner_id]
                if owner_id not in task.depends_on and task.task_id not in owner_task.depends_on:
                    return _row(
                        "no_unapproved_path_overlap",
                        CriterionResult.NOT_VALID,
                        f"path {target.path} shared by {owner_id} and {task.task_id} without declared dependency",
                    )
            owners.setdefault(target.path, task.task_id)
    return _row("no_unapproved_path_overlap", CriterionResult.VALID, "target paths unique or explicitly dependent")


def check_capability_reuse_evidence(plan: ImplementationPlan) -> PreflightCriterionRow:
    for task in plan.tasks:
        for reuse in task.capability_reuse:
            if (
                reuse.coverage in (CapabilityCoverage.PARTIAL, CapabilityCoverage.NOT_COVERED)
                and not reuse.evidence_refs
            ):
                return _row(
                    "capability_reuse_evidence_present",
                    CriterionResult.NOT_VALID,
                    f"task {task.task_id}: capability {reuse.capability!r} lacks evidence",
                )
    return _row("capability_reuse_evidence_present", CriterionResult.VALID, "reuse decisions carry evidence")


def check_covered_not_reimplemented(plan: ImplementationPlan) -> PreflightCriterionRow:
    for task in plan.tasks:
        for reuse in task.capability_reuse:
            if reuse.coverage is CapabilityCoverage.COVERED and reuse.custom_implementation_decision:
                return _row(
                    "covered_capability_not_reimplemented",
                    CriterionResult.NOT_VALID,
                    f"task {task.task_id}: covered capability {reuse.capability!r} must not be reimplemented",
                )
    return _row("covered_capability_not_reimplemented", CriterionResult.VALID, "no covered capability reimplemented")


def check_partial_remaining_responsibility(plan: ImplementationPlan) -> PreflightCriterionRow:
    for task in plan.tasks:
        for reuse in task.capability_reuse:
            if reuse.coverage is CapabilityCoverage.PARTIAL and not reuse.remaining_custom_responsibility:
                return _row(
                    "partial_capability_has_remaining_responsibility",
                    CriterionResult.NOT_VALID,
                    f"task {task.task_id}: partial capability {reuse.capability!r} names no remaining responsibility",
                )
    return _row("partial_capability_has_remaining_responsibility", CriterionResult.VALID, "partial capabilities scoped")


def check_expected_results_present(plan: ImplementationPlan) -> PreflightCriterionRow:
    for task in plan.tasks:
        if not task.expected_result:
            return _row(
                "task_expected_results_present",
                CriterionResult.NOT_VALID,
                f"task {task.task_id} has no expected result",
            )
    return _row("task_expected_results_present", CriterionResult.VALID, "every task declares an expected result")


def check_task_validation_present(plan: ImplementationPlan) -> PreflightCriterionRow:
    for task in plan.tasks:
        if not task.validation_steps:
            return _row(
                "task_validation_present", CriterionResult.NOT_VALID, f"task {task.task_id} has no validation steps"
            )
    return _row("task_validation_present", CriterionResult.VALID, "every task declares validation")


def check_integration_checks_when_needed(plan: ImplementationPlan) -> PreflightCriterionRow:
    if len(plan.tasks) > 1 and not plan.integration_checks:
        return _row(
            "integration_checks_present_when_needed",
            CriterionResult.NOT_VALID,
            "multiple tasks require integration checks",
        )
    return _row(
        "integration_checks_present_when_needed", CriterionResult.VALID, "integration checks present when needed"
    )


def check_required_artifacts_present(required: Mapping[str, bool]) -> PreflightCriterionRow:
    missing = sorted(key for key, present in required.items() if not present)
    if missing:
        return _row("required_artifacts_present", CriterionResult.NOT_VALID, f"missing artifacts: {missing}")
    return _row("required_artifacts_present", CriterionResult.VALID, "all required artifacts present")


def run_preflight(
    *,
    plan: ImplementationPlan,
    checkpoint: SourceCheckpoint,
    target_root: Path,
    required_artifacts: Mapping[str, bool],
    checked_at: datetime | None = None,
) -> PreflightResult:
    """Run the 14 declared preflight checks and compose the overall criterion:
    any not_valid -> not_valid; else any uncertainty -> uncertainty; else valid."""
    rows = (
        check_source_checkpoint_freshness(checkpoint, target_root),
        check_plan_schema_valid(plan),
        check_requirement_trace(plan),
        check_no_uncertainty_in_build_tasks(plan),
        check_all_target_paths_mapped(plan),
        check_target_dispositions_declared(plan),
        check_no_unapproved_path_overlap(plan),
        check_capability_reuse_evidence(plan),
        check_covered_not_reimplemented(plan),
        check_partial_remaining_responsibility(plan),
        check_expected_results_present(plan),
        check_task_validation_present(plan),
        check_integration_checks_when_needed(plan),
        check_required_artifacts_present(required_artifacts),
    )
    if any(row.criterion is CriterionResult.NOT_VALID for row in rows):
        overall = CriterionResult.NOT_VALID
    elif any(row.criterion is CriterionResult.UNCERTAINTY for row in rows):
        overall = CriterionResult.UNCERTAINTY
    else:
        overall = CriterionResult.VALID
    return PreflightResult(criterion=overall, criteria_results=rows, checked_at=checked_at or datetime.now(UTC))


def _require_model(payload: Mapping[str, Any], key: str, model_type: type[BaseModel]) -> Any:
    value = payload.get(key)
    if value is None:
        raise PlanningOpsError(f"deterministic operation payload missing {key!r}")
    if isinstance(value, BaseModel):
        return value
    try:
        return model_type.model_validate(value)
    except ValidationError as exc:
        raise PlanningOpsError(f"payload {key!r} rejected: {exc}") from exc


def freeze_plan_operation(payload: Mapping[str, Any], context: StageContext) -> Mapping[str, Any]:
    plan = _require_model(payload, "implementation_plan", ImplementationPlan)
    checkpoint = _require_model(payload, "source_checkpoint", SourceCheckpoint)
    definition_version = int(payload.get("definition_version") or context.run.definition_version)
    frozen = freeze_plan(plan=plan, checkpoint=checkpoint, definition_version=definition_version)
    return {"frozen_plan": frozen, "frozen_plan_hash": frozen.frozen_plan_hash}


def preflight_check_operation(payload: Mapping[str, Any], context: StageContext) -> Mapping[str, Any]:
    plan = _require_model(payload, "implementation_plan", ImplementationPlan)
    checkpoint = _require_model(payload, "source_checkpoint", SourceCheckpoint)
    target_root_value = payload.get("target_root")
    if not target_root_value:
        raise PlanningOpsError("preflight payload missing target_root")
    required = payload.get("required_artifacts") or {}
    result = run_preflight(
        plan=plan,
        checkpoint=checkpoint,
        target_root=Path(str(target_root_value)),
        required_artifacts={str(key): bool(value) for key, value in dict(required).items()},
    )
    return {"preflight_result": result}


PLANNING_OPERATIONS: Mapping[str, DeterministicOperation] = {
    "freeze_plan": freeze_plan_operation,
    "preflight_check": preflight_check_operation,
}
