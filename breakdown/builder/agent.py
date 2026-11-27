"""Builder agent: executes approved BuildTasks inside an authorized sandbox.

Stage: build_execution. The Builder applies one approved cohesive task at
a time, compares actual observation to the expected result, and returns
evidence-backed task results. It never changes the plan or approvals,
never adds target paths, never declares success, and never authorizes
synchronization. Runtime independently detects changed paths and alone
authorizes synchronization of approved paths only (Phase 2 safety
boundary).
"""

from __future__ import annotations

from pathlib import Path

from breakdown.agents.prompt import load_agent_prompt
from breakdown.shared.base import RoleOperationError
from breakdown.shared.models import (
    BuildExecutionInput,
    BuildExecutionOutput,
    BuildTask,
    CheckResult,
    CodingBackend,
    CodingBackendRequest,
    CodingBackendResult,
    CriterionResult,
    ExecutionResult,
    StageContext,
    TaskResult,
    TokenUsage,
    validate_target_path,
)

PER_TASK_CORRECTION_CAP = 2
STOP_CRITERIA = frozenset({CriterionResult.NOT_VALID, CriterionResult.UNCERTAINTY})


class Builder:
    def __init__(self, *, backend: CodingBackend, sandbox_root: Path) -> None:
        self._backend = backend
        self._sandbox_root = Path(sandbox_root)
        self._agent_instructions = load_agent_prompt(__file__)
        # Accumulated coding-backend usage; runtime budget enforcement reads it.
        self.last_usage: TokenUsage | None = None

    async def execute_build(self, input_value: BuildExecutionInput, context: StageContext) -> BuildExecutionOutput:
        _revalidate_bindings(input_value)
        self.last_usage = None
        ordered = sorted(input_value.implementation_plan.tasks, key=lambda task: task.sequence)
        stop_criteria = (
            frozenset(CriterionResult(value) for value in input_value.stop_on_criterion)
            if input_value.stop_on_criterion
            else STOP_CRITERIA
        )
        results: list[TaskResult] = []
        applied: list[str] = []
        stopped = False
        for task in ordered:
            if stopped:
                results.append(
                    TaskResult(
                        task_id=task.task_id,
                        sequence=task.sequence,
                        criterion=CriterionResult.UNCERTAINTY,
                        execution_result=ExecutionResult.SKIPPED,
                        expected=task.expected_result,
                        actual_observation="skipped: build stopped before this task",
                    )
                )
                continue
            result = await self._execute_task(task)
            results.append(result)
            for changed_path in result.reported_changed_paths:
                if changed_path not in applied:
                    applied.append(changed_path)
            if result.criterion in stop_criteria:
                stopped = True
        prepared = not stopped and all(row.criterion is CriterionResult.VALID for row in results)
        return BuildExecutionOutput(
            task_results=tuple(results),
            applied_changes=tuple(applied),
            validation_results=_validation_rows(results),
            observed_changed_paths=tuple(applied),  # builder-reported; runtime verifies independently
            synchronization_prepared=prepared,
            execution_evidence_refs=(),
        )

    async def _execute_task(self, task: BuildTask) -> TaskResult:
        approved_paths = {target.path for target in task.target_paths}
        unsupported_operations = sorted(
            {
                target.disposition
                for target in task.target_paths
                if target.disposition in {"delete", "move"}
            }
        )
        if unsupported_operations:
            return TaskResult(
                task_id=task.task_id,
                sequence=task.sequence,
                criterion=CriterionResult.UNCERTAINTY,
                execution_result=ExecutionResult.BLOCKED,
                expected=task.expected_result,
                actual_observation=(
                    "current coding backend does not support target dispositions: "
                    f"{unsupported_operations}"
                ),
            )

        prior_error = ""
        attempts = 0
        max_attempts = PER_TASK_CORRECTION_CAP + 1
        reported_paths: list[str] = []
        while True:
            attempts += 1
            result = await self._backend.apply_task(
                CodingBackendRequest(
                    task=task,
                    sandbox_root=str(self._sandbox_root),
                    prior_error=prior_error,
                    agent_instructions=self._agent_instructions,
                )
            )
            self._accumulate_usage(result)

            invalid_paths: list[str] = []
            for reported_path in result.reported_changed_paths:
                if reported_path not in reported_paths:
                    reported_paths.append(reported_path)
                try:
                    normalized_path = validate_target_path(reported_path)
                except ValueError:
                    invalid_paths.append(reported_path)
                    continue
                if normalized_path != reported_path or normalized_path not in approved_paths:
                    invalid_paths.append(reported_path)

            if invalid_paths:
                return TaskResult(
                    task_id=task.task_id,
                    sequence=task.sequence,
                    criterion=CriterionResult.NOT_VALID,
                    execution_result=ExecutionResult.BLOCKED,
                    expected=task.expected_result,
                    actual_observation=(
                        f"{result.observation}; backend reported paths outside the exact "
                        f"approved task scope: {sorted(set(invalid_paths))}"
                    ),
                    attempts=attempts,
                    reported_changed_paths=tuple(reported_paths),
                )

            criterion = _criterion_for(result.execution_result)
            missing_paths = approved_paths - set(reported_paths)
            if result.execution_result is ExecutionResult.COMPLETED and missing_paths:
                if attempts < max_attempts:
                    prior_error = (
                        "The completed response omitted changed-path receipts for approved "
                        f"targets: {sorted(missing_paths)}. Complete only those approved targets."
                    )
                    continue
                criterion = CriterionResult.UNCERTAINTY
            elif criterion is CriterionResult.VALID and missing_paths:
                criterion = CriterionResult.UNCERTAINTY

            terminal = (
                criterion is CriterionResult.VALID
                or criterion is CriterionResult.UNCERTAINTY
                or attempts >= max_attempts
                or result.execution_result is ExecutionResult.BLOCKED
            )
            if terminal:
                observation = result.observation
                if result.execution_result is ExecutionResult.COMPLETED and missing_paths:
                    observation = (
                        f"{observation}; backend did not report changes for approved target paths: "
                        f"{sorted(missing_paths)}"
                    )
                return TaskResult(
                    task_id=task.task_id,
                    sequence=task.sequence,
                    criterion=criterion,
                    execution_result=result.execution_result,
                    expected=task.expected_result,
                    actual_observation=observation,
                    attempts=attempts,
                    reported_changed_paths=tuple(reported_paths),
                )
            prior_error = result.observation

    def _accumulate_usage(self, result: CodingBackendResult) -> None:
        """Sum coding-backend usage across all task attempts of this build."""
        if result.usage is None:
            return
        if self.last_usage is None:
            self.last_usage = result.usage
        else:
            self.last_usage = TokenUsage(
                input_tokens=self.last_usage.input_tokens + result.usage.input_tokens,
                output_tokens=self.last_usage.output_tokens + result.usage.output_tokens,
                tool_calls=self.last_usage.tool_calls + result.usage.tool_calls,
            )


def _criterion_for(result: ExecutionResult) -> CriterionResult:
    if result is ExecutionResult.COMPLETED:
        return CriterionResult.VALID
    if result is ExecutionResult.FAILED:
        return CriterionResult.NOT_VALID
    # blocked / not_run / skipped never advance a build
    return CriterionResult.UNCERTAINTY


def _validation_rows(results: list[TaskResult]) -> tuple[CheckResult, ...]:
    return tuple(
        CheckResult(
            check_ref=f"task:{row.task_id}",
            criterion=row.criterion,
            expected=row.expected,
            actual_observation=row.actual_observation,
        )
        for row in results
    )


def _revalidate_bindings(input_value: BuildExecutionInput) -> None:
    """Builder revalidates approval bindings before source execution."""
    if input_value.approved_plan_revision != input_value.implementation_plan.revision:
        raise RoleOperationError("approved plan revision does not match the implementation plan")
    if input_value.preflight_result.criterion is not CriterionResult.VALID:
        raise RoleOperationError("build execution requires a valid preflight result")
    if not input_value.approval_hash:
        raise RoleOperationError("build execution requires an approval hash")
