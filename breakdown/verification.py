"""Phase 3b, D35: Independent verification prompt assembly and response parsing.

Pure functions — the engine only orchestrates the backend call.
"""

from __future__ import annotations

from pathlib import Path

from breakdown.models import (
    BuildVerificationInput,
    BuildVerificationOutput,
    CheckResult,
    ObservedFile,
    VerificationTaskView,
    Settings,
)
from breakdown.tools import RoleBackendRequest


def build_verification_input(
    run_id: str,
    plan: "ImplementationPlan",
    build_output: "BuildExecutionOutput",
    sandbox: Path,
    *,
    max_file_chars: int = 8000,
) -> BuildVerificationInput:
    """Assemble ``BuildVerificationInput`` from the frozen plan, build output,
    and sandbox (reading each task's target files, capped per file)."""

    tasks: tuple[VerificationTaskView, ...] = ()

    for task in build_output.task_tasks:  # type: ignore[attr-defined]
        task_ref = task.task_id
        description = task.responsibility or "build task"
        expected_result = task.expected_result or ""

        observed_files: tuple[ObservedFile, ...] = ()
        for target in task.target_paths:  # type: ignore[attr-defined]
            tpath = target.path  # type: ignore[attr-defined]
            try:
                sandbox_file = sandbox / tpath
                if sandbox_file.exists():
                    raw = sandbox_file.read_text(encoding="utf-8")
                    truncated = len(raw) > max_file_chars
                    content = raw[:max_file_chars]
                else:
                    content = ""
                    truncated = False
            except Exception:  # noqa: BLE001 - best-effort; missing file --> empty
                content = ""
                truncated = False
            observed_files = observed_files + (
                ObservedFile(path=tpath, content=content, truncated=truncated),
            )

        tasks = tasks + (
            VerificationTaskView(
                task_ref=task_ref,
                description=description,
                expected_result=expected_result,
                validation_steps=task.validation_steps or (),
                observed_files=observed_files,
            ),
        )

    return BuildVerificationInput(run_id=run_id, tasks=tasks)


def verification_request(input_: BuildVerificationInput) -> RoleBackendRequest:
    """Wrap a ``BuildVerificationInput`` in a ``RoleBackendRequest`` for the
    verifier backend."""

    return RoleBackendRequest(
        operation="verify_build_task",
        system_prompt="You are an independent grader. Evaluate each task's "
        "output against its rubric. Be precise and do not use the builder's "
        "reasoning.",
        prompt="",  # the prompt is embedded via observed_files
        output_schema=BuildVerificationOutput.model_json_schema(),
        tool_names=(),
        max_tokens=8000,
    )


def parse_verification(
    response: "RoleBackendResponse",
    input_: BuildVerificationInput,
) -> tuple[CheckResult, ...]:
    """Parse a ``RoleBackendResponse`` into a tuple of ``CheckResult``.

    Maps ``uncertainty`` and ``not_valid`` to blocking verdicts (the
    definition's ``stop_on_criterion`` already lists ``uncertainty``).
    """

    results: list[CheckResult] = []

    sv = getattr(response, "structured_output", None)
    if sv is None:
        n = len(input_.tasks)
        return tuple(
            CheckResult(
                check_ref=input_.tasks[i].task_ref,
                criterion="verifier_error",
                expected=input_.tasks[i].expected_result,
                actual_observation="backend returned no structured output",
            )
            for i in range(n)
        )

    tv: VerificationTaskView
    for i, tv in enumerate(input_.tasks):
        vr = getattr(sv, "task_verifications", None)
        if vr is None or i >= len(vr):
            results.append(
                CheckResult(
                    check_ref=tv.task_ref,
                    criterion="not_valid",
                    expected=input_.tasks[i].expected_result,
                    actual_observation="no verdict from verifier",
                )
            )
            continue

        cv = vr[i]
        criterion = cv.criterion or "not_valid"
        expected = tv.expected_result
        actual = cv.actual_observation or ""

        if criterion == "uncertainty":
            results.append(
                CheckResult(
                    check_ref=tv.task_ref,
                    criterion="uncertainty",
                    expected=expected,
                    actual_observation=actual,
                )
            )
        elif criterion == "not_valid":
            results.append(
                CheckResult(
                    check_ref=tv.task_ref,
                    criterion="not_valid",
                    expected=expected,
                    actual_observation=actual,
                )
            )
        else:
            results.append(
                CheckResult(
                    check_ref=tv.task_ref,
                    criterion=criterion,
                    expected=expected,
                    actual_observation=actual,
                )
            )

    return tuple(results)


def verification_failure_reason(results: tuple[CheckResult, ...]) -> str | None:
    """Return a human-readable reason when verification blocks sync.

    Returns ``None`` only when every criterion is ``valid``; ``uncertainty``
    and ``not_valid`` both block, with the returned string naming the offending
    task refs and criteria.
    """

    blocked: list[str] = []
    for cr in results:
        if cr.criterion in ("not_valid", "uncertainty"):
            blocked.append(f"{cr.task_ref}: {cr.criterion} (expected={cr.expected!r})")

    if not blocked:
        return None
    return "; ".join(blocked)