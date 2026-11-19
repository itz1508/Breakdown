"""Phase 3b - D35: verification blocks sync."""

from pathlib import Path
from typing import Any

from breakdown.models import (
    BuildExecutionOutput,
    CriterionResult,
    ExecutionResult,
    ImplementationPlan,
    RoleBackendResponse,
    TaskResult,
    TokenUsage,
)
from breakdown.verification import build_verification_input
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
                        "check_ref": "check-task-1",
                        "criterion": self.criterion.value,
                        "expected": "expected",
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


def test_verifier_absence_preserves_legacy(tmp_path: Path) -> None:
    """D35: existing rows without verifier key still pass (backward compat)."""
    e2e = _E2E(tmp_path)
    record = _run_e2e(e2e)
    assert record.terminal_outcome == "success"
    calc_text = (e2e.target / "src" / "calc.py").read_text(encoding="utf-8")
    assert "def subtract" in calc_text


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


def test_prompt_embeds_sandbox_not_builder(tmp_path: Path) -> None:
    """D35: verification input embeds sandbox files, not builder observations."""
    sandbox = tmp_path / "sandbox"
    (sandbox / "src").mkdir(parents=True)
    (sandbox / "src" / "calc.py").write_text("def subtract(a, b):\n    return a - b\n", encoding="utf-8")

    plan = ImplementationPlan.model_validate(PLAN_OUTPUT["implementation_plan"])
    task_result = TaskResult(
        task_id="task-1",
        sequence=1,
        criterion=CriterionResult.VALID,
        execution_result=ExecutionResult.COMPLETED,
        expected="subtract implemented",
        actual_observation="def subtract added",
        attempts=1,
    )
    build_output = BuildExecutionOutput(
        task_results=[task_result],
        validation_results=[],
    )
    vb_input = build_verification_input("run-1", plan, build_output, sandbox)
    assert len(vb_input.tasks) == 1
    observed = vb_input.tasks[0].observed_files
    assert any(f.path == "src/calc.py" and "def subtract" in f.content for f in observed)


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
