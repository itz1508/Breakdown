"""Phase 3b - D35: verification blocks sync."""

from pathlib import Path
from typing import Any
from breakdown.shared.models import (
    BuildExecutionOutput,
    BuildVerificationInput,
    BuildVerificationOutput,
    CriterionResult,
    ExecutionResult,
    ImplementationPlan,
    RoleBackendResponse,
    TaskResult,
    TokenUsage,
    ValidationStep,
)
from breakdown.system.runtime.verification import (
    build_verification_input,
    parse_verification,
    verification_request,
)

from tests.test_engine_lifecycle import (
    _E2E,
    PLAN_OUTPUT,
)


class _ScriptedVerifierBackend:
    def __init__(self, criterion: CriterionResult = CriterionResult.VALID) -> None:
        self.criterion = criterion

    async def generate(self, request: Any) -> RoleBackendResponse:
        return RoleBackendResponse(
            structured_output={
                "task_verifications": [
                    {
                        "check_ref": "task-1",
                        "criterion": self.criterion.value,
                        "expected": "src/calc.py defines subtract(a, b) and returns a - b",
                        "actual_observation": "verifier check result",
                    }
                ]
            },
            text="",
            usage=TokenUsage(input_tokens=50, output_tokens=50, tool_calls=1),
            provider="fake",
            model="fake-verifier",
        )


class _RaisingVerifierBackend:
    async def generate(self, request: Any) -> RoleBackendResponse:
        raise RuntimeError("simulated verifier transport failure")


def _run_e2e(e2e: _E2E) -> Any:
    record = e2e.engine.start_run("Add subtract to src/calc.py with a test.", user_identity="user@example.com")
    record = e2e.engine.advance(run_id=record.run_id)
    record = e2e.engine.record_decision(run_id=record.run_id, action="approve", user_identity="user@example.com")
    record = e2e.engine.advance(run_id=record.run_id)
    record = e2e.engine.record_decision(run_id=record.run_id, action="approve", user_identity="user@example.com")
    return e2e.engine.advance(run_id=record.run_id)


def test_verifier_rejection_blocks_sync(tmp_path: Path) -> None:
    """D35: verifier rejection blocks sync despite builder claiming valid."""
    e2e = _E2E(tmp_path)
    base_factory = e2e.engine.role_factory

    def factory_with_rejecting_verifier(sandbox: Path | None) -> dict[str, object]:
        roles = dict(base_factory(sandbox))
        roles["verifier"] = _ScriptedVerifierBackend(CriterionResult.NOT_VALID)
        return roles

    e2e.engine.role_factory = factory_with_rejecting_verifier

    record = _run_e2e(e2e)
    assert record.terminal_outcome == "failed"
    assert "synchronization blocked" in (record.reason or "")
    # Target repo file must NOT contain subtract
    calc_text = (e2e.target / "src" / "calc.py").read_text(encoding="utf-8")
    assert "def subtract" not in calc_text


def test_verifier_absence_blocks_synchronization(tmp_path: Path) -> None:
    """A missing independent verifier must never fall back to Builder self-report."""
    e2e = _E2E(tmp_path)
    base_factory = e2e.engine.role_factory

    def factory_without_verifier(sandbox: Path | None) -> dict[str, object]:
        roles = dict(base_factory(sandbox))
        roles.pop("verifier", None)
        return roles

    e2e.engine.role_factory = factory_without_verifier
    record = _run_e2e(e2e)
    assert record.terminal_outcome == "failed"
    assert "synchronization blocked" in (record.reason or "")
    assert "independent_verification" in record.produced_artifacts
    verification_ref = record.produced_artifacts["independent_verification"]
    verification = e2e.artifacts.get_model(
        BuildVerificationOutput,
        verification_ref.artifact_key,
        verification_ref.revision,
    )
    assert "not configured" in verification.task_verifications[0].actual_observation
    calc_text = (e2e.target / "src" / "calc.py").read_text(encoding="utf-8")
    assert "def subtract" not in calc_text


def test_verifier_failure_is_conservative(tmp_path: Path) -> None:
    """D35: verifier backend raises -> terminal failed, no crash."""
    e2e = _E2E(tmp_path)
    base_factory = e2e.engine.role_factory

    def factory_with_raising_verifier(sandbox: Path | None) -> dict[str, object]:
        roles = dict(base_factory(sandbox))
        roles["verifier"] = _RaisingVerifierBackend()
        return roles

    e2e.engine.role_factory = factory_with_raising_verifier

    record = _run_e2e(e2e)
    assert record.terminal_outcome == "failed"
    assert "synchronization blocked" in (record.reason or "")
    calc_text = (e2e.target / "src" / "calc.py").read_text(encoding="utf-8")
    assert "def subtract" not in calc_text


def test_prompt_embeds_sandbox_and_validation_steps(tmp_path: Path) -> None:
    """The verifier receives complete sandbox observations and validation expectations."""
    sandbox = tmp_path / "sandbox"
    (sandbox / "src").mkdir(parents=True)
    (sandbox / "src" / "calc.py").write_text(
        "def subtract(a, b):\\n    return a - b\\n", encoding="utf-8"
    )

    plan = ImplementationPlan.model_validate(PLAN_OUTPUT["implementation_plan"])
    task_result = TaskResult(
        task_id="task-1",
        sequence=1,
        criterion=CriterionResult.VALID,
        execution_result=ExecutionResult.COMPLETED,
        expected="subtract implemented",
        actual_observation="Builder says subtract added",
        attempts=1,
    )
    build_output = BuildExecutionOutput(task_results=[task_result], validation_results=[])
    verifier_input = build_verification_input("run-1", plan, build_output, sandbox)
    observed = verifier_input.tasks[0].observed_files
    assert any(
        file.path == "src/calc.py"
        and file.status == "read"
        and "def subtract" in file.content
        for file in observed
    )

    request = verification_request(verifier_input)
    assert "def subtract" in request.prompt
    assert "read src/calc.py and verify subtract is defined and returns a - b" in request.prompt
    assert '"expected": "subtract is defined and returns a - b"' in request.prompt
    assert "independent build verifier" in request.system_prompt


def test_verification_downgrades_unexecuted_command_to_uncertainty() -> None:
    verifier_input = BuildVerificationInput(
        run_id="run-1",
        tasks=(
            {
                "task_ref": "task-1",
                "description": "run unit tests",
                "expected_result": "pytest passes",
                "validation_steps": (
                    ValidationStep(
                        step_id="test-1",
                        description="run pytest",
                        command_or_observation="pytest -q",
                        expected="all tests pass",
                        kind="command",
                    ),
                ),
                "observed_files": (),
            },
        ),
    )
    response = RoleBackendResponse(
        structured_output={
            "task_verifications": [
                {
                    "check_ref": "task-1",
                    "criterion": "valid",
                    "expected": "pytest passes",
                    "actual_observation": "the source appears correct",
                }
            ]
        },
        text="",
        provider="test",
        model="test",
    )
    verdicts = parse_verification(response, verifier_input)
    assert verdicts[0].criterion is CriterionResult.UNCERTAINTY
    assert "were not executed by the Host" in verdicts[0].actual_observation


def test_verification_marks_missing_files_and_rejects_valid_verdict(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    plan = ImplementationPlan.model_validate(PLAN_OUTPUT["implementation_plan"])
    task_result = TaskResult(
        task_id="task-1",
        sequence=1,
        criterion=CriterionResult.VALID,
        execution_result=ExecutionResult.COMPLETED,
        expected="subtract implemented",
        actual_observation="Builder says done",
    )
    verifier_input = build_verification_input(
        "run-1", plan, BuildExecutionOutput(task_results=[task_result]), sandbox
    )
    assert verifier_input.tasks[0].observed_files[0].status == "missing"
    response = RoleBackendResponse(
        structured_output={
            "task_verifications": [
                {
                    "check_ref": "task-1",
                    "criterion": "valid",
                    "expected": "subtract implemented",
                    "actual_observation": "looks complete",
                }
            ]
        },
        text="",
        provider="test",
        model="test",
    )
    verdicts = parse_verification(response, verifier_input)
    assert verdicts[0].criterion is CriterionResult.NOT_VALID


def test_verification_rejects_mismatched_expected_result() -> None:
    verifier_input = BuildVerificationInput(
        run_id="run-1",
        tasks=(
            {
                "task_ref": "task-1",
                "description": "implement subtract",
                "expected_result": "subtract(3, 2) == 1",
                "validation_steps": (),
                "observed_files": (),
            },
        ),
    )
    response = RoleBackendResponse(
        structured_output={
            "task_verifications": [
                {
                    "check_ref": "task-1",
                    "criterion": "valid",
                    "expected": "subtract(3, 2) == 2",
                    "actual_observation": "completed",
                }
            ]
        },
        text="",
        provider="test",
        model="test",
    )
    verdicts = parse_verification(response, verifier_input)
    assert verdicts[0].criterion is CriterionResult.NOT_VALID
    assert "different expected result" in verdicts[0].actual_observation


def test_verification_rejects_wrong_and_missing_task_refs() -> None:
    verifier_input = BuildVerificationInput(
        run_id="run-1",
        tasks=(
            {
                "task_ref": "task-1",
                "description": "first",
                "expected_result": "first done",
                "validation_steps": (),
                "observed_files": (),
            },
            {
                "task_ref": "task-2",
                "description": "second",
                "expected_result": "second done",
                "validation_steps": (),
                "observed_files": (),
            },
        ),
    )
    wrong_ref = RoleBackendResponse(
        structured_output={
            "task_verifications": [
                {
                    "check_ref": "not-a-task",
                    "criterion": "valid",
                    "expected": "first done",
                    "actual_observation": "done",
                }
            ]
        },
        text="",
        provider="test",
        model="test",
    )
    wrong_verdicts = parse_verification(wrong_ref, verifier_input)
    assert all(verdict.criterion is CriterionResult.NOT_VALID for verdict in wrong_verdicts)

    partial = RoleBackendResponse(
        structured_output={
            "task_verifications": [
                {
                    "check_ref": "task-1",
                    "criterion": "valid",
                    "expected": "first done",
                    "actual_observation": "first done",
                }
            ]
        },
        text="",
        provider="test",
        model="test",
    )
    partial_verdicts = parse_verification(partial, verifier_input)
    assert len(partial_verdicts) == 2
    assert partial_verdicts[0].criterion is CriterionResult.VALID
    assert partial_verdicts[1].criterion is CriterionResult.NOT_VALID


def test_offline_demo_verifier_checks_actual_sandbox_observation() -> None:
    import asyncio

    from breakdown.shared.models import ObservedFile, VerificationTaskView
    from breakdown.system.runtime.demo import OfflineDemoRoleBackend

    verification_input = BuildVerificationInput(
        run_id="demo-run",
        tasks=(
            VerificationTaskView(
                task_ref="demo-task-1",
                description="create the demo change record",
                expected_result="DEMO_CHANGE.md contains the request text provided to this run",
                validation_steps=(
                    ValidationStep(
                        step_id="demo-v-1",
                        description="inspect demo change file",
                        command_or_observation="read DEMO_CHANGE.md and verify the exact request text is present",
                        expected="the current request text is present",
                        kind="observation",
                    ),
                ),
                observed_files=(
                    ObservedFile(
                        path="DEMO_CHANGE.md",
                        disposition="create",
                        content="# Demo change\\n\\nRequest: exact demo request\\n",
                        status="read",
                    ),
                ),
            ),
        ),
    )
    backend = OfflineDemoRoleBackend("exact demo request")
    response = asyncio.run(backend.generate(verification_request(verification_input)))
    verdicts = parse_verification(response, verification_input)

    assert verdicts[0].criterion is CriterionResult.VALID
    assert "Host observed the exact request text" in verdicts[0].actual_observation


def test_offline_demo_verifier_does_not_claim_unexecuted_commands() -> None:
    import asyncio

    from breakdown.shared.models import ObservedFile, VerificationTaskView
    from breakdown.system.runtime.demo import OfflineDemoRoleBackend

    verification_input = BuildVerificationInput(
        run_id="demo-run",
        tasks=(
            VerificationTaskView(
                task_ref="demo-task-1",
                description="run tests",
                expected_result="pytest passes",
                validation_steps=(
                    ValidationStep(
                        step_id="demo-v-1",
                        description="run pytest",
                        command_or_observation="pytest -q",
                        expected="all tests pass",
                        kind="command",
                    ),
                ),
                observed_files=(
                    ObservedFile(
                        path="DEMO_CHANGE.md",
                        disposition="create",
                        content="Request: exact demo request",
                        status="read",
                    ),
                ),
            ),
        ),
    )
    backend = OfflineDemoRoleBackend("exact demo request")
    response = asyncio.run(backend.generate(verification_request(verification_input)))
    verdicts = parse_verification(response, verification_input)

    assert verdicts[0].criterion is CriterionResult.UNCERTAINTY
    assert "cannot execute command steps" in verdicts[0].actual_observation


def test_verification_rejects_missing_expected_result() -> None:
    verifier_input = BuildVerificationInput(
        run_id="run-1",
        tasks=(
            {
                "task_ref": "task-1",
                "description": "implement subtract",
                "expected_result": "subtract implemented",
                "validation_steps": (),
                "observed_files": (),
            },
        ),
    )
    response = RoleBackendResponse(
        structured_output={
            "task_verifications": [
                {
                    "check_ref": "task-1",
                    "criterion": "valid",
                    "actual_observation": "looks complete",
                }
            ]
        },
        text="",
        provider="test",
        model="test",
    )
    verdicts = parse_verification(response, verifier_input)
    assert verdicts[0].criterion is CriterionResult.NOT_VALID
    assert "omitted or changed" in verdicts[0].actual_observation


def test_verification_rejects_delete_target_that_still_exists() -> None:
    from breakdown.shared.models import ObservedFile, VerificationTaskView

    verifier_input = BuildVerificationInput(
        run_id="run-1",
        tasks=(
            VerificationTaskView(
                task_ref="task-delete",
                description="delete old file",
                expected_result="old file is absent",
                validation_steps=(),
                observed_files=(
                    ObservedFile(
                        path="old.py",
                        disposition="delete",
                        content="still here",
                        status="read",
                    ),
                ),
            ),
        ),
    )
    response = RoleBackendResponse(
        structured_output={
            "task_verifications": [
                {
                    "check_ref": "task-delete",
                    "criterion": "valid",
                    "expected": "old file is absent",
                    "actual_observation": "deleted",
                }
            ]
        },
        text="",
        provider="test",
        model="test",
    )
    verdicts = parse_verification(response, verifier_input)
    assert verdicts[0].criterion is CriterionResult.NOT_VALID
    assert "still present" in verdicts[0].actual_observation


def test_offline_demo_verifier_checks_actual_sandbox_observation() -> None:
    import asyncio

    from breakdown.shared.models import ObservedFile, VerificationTaskView
    from breakdown.system.runtime.demo import OfflineDemoRoleBackend

    verification_input = BuildVerificationInput(
        run_id="demo-run",
        tasks=(
            VerificationTaskView(
                task_ref="demo-task-1",
                description="create the demo change record",
                expected_result="DEMO_CHANGE.md contains the request text provided to this run",
                validation_steps=(
                    ValidationStep(
                        step_id="demo-v-1",
                        description="inspect demo change file",
                        command_or_observation="read DEMO_CHANGE.md and verify the exact request text is present",
                        expected="the current request text is present",
                        kind="observation",
                    ),
                ),
                observed_files=(
                    ObservedFile(
                        path="DEMO_CHANGE.md",
                        disposition="create",
                        content="# Demo change\\n\\nRequest: exact demo request\\n",
                        status="read",
                    ),
                ),
            ),
        ),
    )
    backend = OfflineDemoRoleBackend("exact demo request")
    response = asyncio.run(backend.generate(verification_request(verification_input)))
    verdicts = parse_verification(response, verification_input)

    assert verdicts[0].criterion is CriterionResult.VALID
    assert "Host observed the exact request text" in verdicts[0].actual_observation


def test_offline_demo_verifier_does_not_claim_unexecuted_commands() -> None:
    import asyncio

    from breakdown.shared.models import ObservedFile, VerificationTaskView
    from breakdown.system.runtime.demo import OfflineDemoRoleBackend

    verification_input = BuildVerificationInput(
        run_id="demo-run",
        tasks=(
            VerificationTaskView(
                task_ref="demo-task-1",
                description="run tests",
                expected_result="pytest passes",
                validation_steps=(
                    ValidationStep(
                        step_id="demo-v-1",
                        description="run pytest",
                        command_or_observation="pytest -q",
                        expected="all tests pass",
                        kind="command",
                    ),
                ),
                observed_files=(
                    ObservedFile(
                        path="DEMO_CHANGE.md",
                        disposition="create",
                        content="Request: exact demo request",
                        status="read",
                    ),
                ),
            ),
        ),
    )
    backend = OfflineDemoRoleBackend("exact demo request")
    response = asyncio.run(backend.generate(verification_request(verification_input)))
    verdicts = parse_verification(response, verification_input)

    assert verdicts[0].criterion is CriterionResult.UNCERTAINTY
    assert "cannot execute command steps" in verdicts[0].actual_observation


def test_verifier_happy_path_authorizes_sync(tmp_path: Path) -> None:
    """D35: builder + verifier all valid -> sync authorized, run succeeds."""
    e2e = _E2E(tmp_path)
    base_factory = e2e.engine.role_factory

    def factory_with_passing_verifier(sandbox: Path | None) -> dict[str, object]:
        roles = dict(base_factory(sandbox))
        roles["verifier"] = _ScriptedVerifierBackend(CriterionResult.VALID)
        return roles

    e2e.engine.role_factory = factory_with_passing_verifier

    record = _run_e2e(e2e)
    assert record.terminal_outcome == "success"
    calc_text = (e2e.target / "src" / "calc.py").read_text(encoding="utf-8")
    assert "def subtract" in calc_text
