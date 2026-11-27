"""P2-T7b — budget enforcement, recovery routing, stage timeouts, uncertainty loopback."""

from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from breakdown.shared.models import (
    CodingBackendResult,
    EventType,
    ExecutionResult,
    FailureRecord,
    RoleBackendResponse,
    RunState,
    TokenUsage,
)
from breakdown.system.runtime.approvals import ApprovalManager
from breakdown.system.runtime.engine import EngineStores, WorkflowEngine, load_workflow
from breakdown.system.safety import SafetyBoundary
from breakdown.system.storage.artifact_store import ArtifactStore
from breakdown.system.storage.events import EventStore
from breakdown.system.storage.run_store import RunStore

REPO_ROOT = Path(__file__).resolve().parents[3]

# Shared e2e constants live in test_engine_lifecycle.py; load by path because
# pytest runs in importlib mode (no sys.path insertion for sibling test modules).
_spec = importlib.util.spec_from_file_location(
    "e2e_lifecycle", Path(__file__).resolve().parent / "test_engine_lifecycle.py"
)
assert _spec is not None and _spec.loader is not None
_lifecycle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lifecycle)
PROPOSAL_OUTPUT: dict[str, Any] = _lifecycle.PROPOSAL_OUTPUT
RESEARCH_OUTPUT: dict[str, Any] = _lifecycle.RESEARCH_OUTPUT
FINDINGS_OUTPUT: dict[str, Any] = _lifecycle.FINDINGS_OUTPUT
PLAN_OUTPUT: dict[str, Any] = _lifecycle.PLAN_OUTPUT

SMALL_USAGE = TokenUsage(input_tokens=100, output_tokens=200, tool_calls=1)


class ScriptedBackend:
    """Canned outputs with configurable usage, transient/permanent failures, and delays."""

    def __init__(
        self,
        *,
        usage: TokenUsage | None = None,
        fail_times: Mapping[str, int] | None = None,
        always_fail: Mapping[str, bool] | None = None,
        delay_operations: Mapping[str, float] | None = None,
    ) -> None:
        self._scripted: dict[str, Mapping[str, Any]] = {
            "create_research_proposal": PROPOSAL_OUTPUT,
            "execute_research": RESEARCH_OUTPUT,
            "review_research_findings": FINDINGS_OUTPUT,
            "create_implementation_plan": PLAN_OUTPUT,
        }
        self._usage = usage or SMALL_USAGE
        self._fail_times = dict(fail_times or {})
        self._always_fail = dict(always_fail or {})
        self._delay = dict(delay_operations or {})
        self.calls: dict[str, int] = {}

    async def generate(self, request: Any) -> Any:
        op = request.operation
        self.calls[op] = self.calls.get(op, 0) + 1
        if self._always_fail.get(op):
            raise RuntimeError(f"scripted permanent failure for {op}")
        if self.calls[op] <= self._fail_times.get(op, 0):
            raise RuntimeError(f"scripted transient failure for {op} (call {self.calls[op]})")
        delay = self._delay.get(op)
        if delay:
            await asyncio.sleep(delay)
        payload = self._scripted.get(op)
        if payload is None:
            raise RuntimeError(f"no scripted output for {op}")
        return RoleBackendResponse(
            structured_output=payload, text="", usage=self._usage, provider="fake", model="fake-t7b"
        )


class ScriptedCodingBackend:
    """apply_task outcomes by attempt: complete writes the file; blocked/failed do not."""

    def __init__(self, outcomes: tuple[str, ...] = ("complete",)) -> None:
        self._outcomes = outcomes
        self.calls = 0

    async def apply_task(self, request: Any) -> Any:
        outcome = self._outcomes[min(self.calls, len(self._outcomes) - 1)]
        self.calls += 1
        usage = TokenUsage(input_tokens=10, output_tokens=10, tool_calls=1)
        if outcome == "complete":
            sandbox = Path(request.sandbox_root)
            (sandbox / "src" / "calc.py").write_text(
                "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
                encoding="utf-8",
            )
            return CodingBackendResult(
                execution_result=ExecutionResult.COMPLETED,
                observation="subtract implemented in sandbox",
                reported_changed_paths=("src/calc.py",),
                usage=usage,
            )
        if outcome == "blocked":
            return CodingBackendResult(
                execution_result=ExecutionResult.BLOCKED,
                observation="newly required path discovered",
                reported_changed_paths=(),
                usage=usage,
            )
        return CodingBackendResult(
            execution_result=ExecutionResult.FAILED, observation="task failed", reported_changed_paths=(), usage=usage
        )


def _budget_definition(
    tmp_path: Path,
    *,
    max_tokens: int = 500_000,
    max_tool_calls: int = 200,
    stage_cap: int = 40_000,
    reserve: int = 50_000,
    timeout_overrides: Mapping[str, int] | None = None,
) -> Path:
    """Copy of breakdown.yaml with adjusted cost_budget numbers (definition stays authoritative)."""
    raw = yaml.safe_load((REPO_ROOT / "breakdown.yaml").read_text(encoding="utf-8"))
    raw["cost_budget"]["per_workflow"]["max_tokens"] = max_tokens
    raw["cost_budget"]["per_workflow"]["max_tool_calls"] = max_tool_calls
    raw["cost_budget"]["per_stage"]["default_max_tokens"] = stage_cap
    raw["cost_budget"]["per_stage"]["completion_reserve"] = reserve
    if timeout_overrides:
        for stage in raw["stages"]:
            if stage["id"] in timeout_overrides:
                stage["timeout_seconds"] = timeout_overrides[stage["id"]]
    path = tmp_path / "budget.breakdown.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


class Harness:
    """Target repo + stores + engine wired with configurable scripted fakes."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        definition_path: Path | None = None,
        usage: TokenUsage | None = None,
        role_fail_times: Mapping[str, int] | None = None,
        role_always_fail: Mapping[str, bool] | None = None,
        delay: Mapping[str, float] | None = None,
        coding_outcomes: tuple[str, ...] = ("complete",),
    ) -> None:
        self.target = tmp_path / "repo"
        (self.target / "src").mkdir(parents=True)
        (self.target / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        state = tmp_path / "state"
        self.artifacts = ArtifactStore(state)
        self.events = EventStore(state)
        self.runs = RunStore(state)
        self.safety = SafetyBoundary(target_root=self.target, state_root=state)
        self.definition = load_workflow(definition_path or (REPO_ROOT / "breakdown.yaml"))
        from breakdown.auditor.agent import Auditor
        from breakdown.builder.agent import Builder
        from breakdown.planner.agent import Planner
        from breakdown.researcher.agent import Researcher
        from breakdown.system.runtime.contracts import build_contract_registry
        from breakdown.system.tools.toolkit import RoleToolkit

        self.contracts = build_contract_registry(self.definition)
        self.approvals = ApprovalManager(
            artifacts=self.artifacts, events=self.events, runs=self.runs, definition=self.definition
        )
        self.backend = ScriptedBackend(
            usage=usage, fail_times=role_fail_times, always_fail=role_always_fail, delay_operations=delay
        )
        self.coding = ScriptedCodingBackend(coding_outcomes)

        def role_factory(sandbox: Path | None) -> Mapping[str, object]:
            return {
                "auditor": Auditor(backend=self.backend, tools=RoleToolkit(role="auditor", root=self.target)),
                "researcher": Researcher(backend=self.backend, tools=RoleToolkit(role="researcher", root=self.target)),
                "planner": Planner(backend=self.backend, tools=RoleToolkit(role="planner", root=self.target)),
                "builder": Builder(backend=self.coding, sandbox_root=sandbox or self.target),
            }

        self.engine = WorkflowEngine(
            definition=self.definition,
            contracts=self.contracts,
            stores=EngineStores(artifacts=self.artifacts, events=self.events, runs=self.runs, safety=self.safety),
            approvals=self.approvals,
            role_factory=role_factory,
        )

    def run_to_terminal(self, max_steps: int = 40) -> Any:
        record = self.engine.start_run("request", user_identity="u")
        for _ in range(max_steps):
            record = self.engine.advance(record.run_id)
            if record.state is RunState.TERMINAL:
                return record
            if record.state is RunState.AWAITING_DECISION:
                record = self.engine.record_decision(record.run_id, "approve", user_identity="u")
        raise AssertionError("run did not reach terminal state within max_steps")


def test_per_stage_cap_exhausts_budget(tmp_path: Path) -> None:
    # 45k tokens on the first activation exceeds the 40k per-stage cap.
    h = Harness(tmp_path, usage=TokenUsage(input_tokens=30_000, output_tokens=15_000, tool_calls=1))
    record = h.run_to_terminal()
    assert record.state is RunState.TERMINAL
    assert record.terminal_outcome == "failed"
    assert record.reason == "budget_exhausted"
    assert "budget_exhausted_record" in record.produced_artifacts
    assert "failure_record" in record.produced_artifacts
    assert "retained_evidence" in record.produced_artifacts
    failure_ref = record.produced_artifacts["failure_record"]
    failure = h.artifacts.get_model(FailureRecord, failure_ref.artifact_key, failure_ref.revision)
    assert failure.error_type == "budget_exhausted"


def test_reserve_exhaustion_and_threshold_event(tmp_path: Path) -> None:
    definition = _budget_definition(tmp_path, max_tokens=100_000, stage_cap=200_000, reserve=50_000)
    h = Harness(
        tmp_path,
        definition_path=definition,
        usage=TokenUsage(input_tokens=30_000, output_tokens=15_000, tool_calls=1),
    )
    record = h.engine.start_run("request", user_identity="u")
    run_id = record.run_id
    record = h.engine.advance(run_id)  # stage 1: 45k used, 55k remaining >= 50k reserve
    assert record.state is RunState.AWAITING_DECISION
    h.engine.record_decision(run_id, "approve", user_identity="u")
    record = h.engine.advance(run_id)  # stage 2: 90k used, 10k remaining < 50k reserve
    assert record.state is RunState.TERMINAL
    assert record.reason == "budget_exhausted"
    types = [event.event_type for event in h.events.load(run_id)]
    assert types.count(EventType.COST_THRESHOLD_APPROACHED) == 1  # crossed 80k on stage 2


def test_workflow_max_tokens_exceeded(tmp_path: Path) -> None:
    definition = _budget_definition(tmp_path, max_tokens=100_000, stage_cap=200_000, reserve=5_000)
    h = Harness(
        tmp_path,
        definition_path=definition,
        usage=TokenUsage(input_tokens=40_000, output_tokens=20_000, tool_calls=1),
    )
    record = h.run_to_terminal()
    assert record.terminal_outcome == "failed"
    assert record.reason == "budget_exhausted"
    assert record.tokens_used > 100_000


def test_max_tool_calls_exceeded(tmp_path: Path) -> None:
    definition = _budget_definition(tmp_path, max_tool_calls=5, stage_cap=200_000, reserve=0)
    h = Harness(tmp_path, definition_path=definition, usage=TokenUsage(input_tokens=10, output_tokens=10, tool_calls=3))
    record = h.run_to_terminal()
    assert record.terminal_outcome == "failed"
    assert record.reason == "budget_exhausted"
    assert record.tool_calls_used > 5


def test_budget_violation_boundaries(tmp_path: Path) -> None:
    h = Harness(tmp_path)  # canonical definition: 500k tokens / 200 calls / 50k reserve
    assert h.engine._budget_violation(0, 0) is None
    assert h.engine._budget_violation(450_000, 0) is None  # remaining == reserve is still ok
    assert h.engine._budget_violation(450_001, 0) is not None
    assert h.engine._budget_violation(500_001, 0) is not None
    assert h.engine._budget_violation(0, 200) is None
    assert h.engine._budget_violation(0, 201) is not None


def test_recovery_retry_then_success(tmp_path: Path) -> None:
    h = Harness(tmp_path, role_fail_times={"create_research_proposal": 1})
    record = h.engine.start_run("request", user_identity="u")
    record = h.engine.advance(record.run_id)  # attempt 1 fails, recovery retry, attempt 2 succeeds
    assert record.state is RunState.AWAITING_DECISION
    assert record.current_stage == "research_approval"
    assert record.stage_attempts["research_proposal"] == 2
    failed = [event for event in h.events.load(record.run_id) if event.event_type is EventType.STAGE_FAILED]
    assert len(failed) == 1
    assert failed[0].payload["recovery"] == "retry"


def test_recovery_exhaustion_routes_failed(tmp_path: Path) -> None:
    h = Harness(tmp_path, role_always_fail={"create_research_proposal": True})
    record = h.run_to_terminal()
    assert record.terminal_outcome == "failed"
    assert record.stage_attempts["research_proposal"] == 3  # initial + 2 recovery attempts
    assert "stage execution failed" in record.reason
    assert "failure_record" in record.produced_artifacts
    assert "retained_evidence" in record.produced_artifacts


def test_stage_timeout_exhausts_recovery(tmp_path: Path) -> None:
    definition = _budget_definition(tmp_path, timeout_overrides={"research_proposal": 1})
    h = Harness(tmp_path, definition_path=definition, delay={"create_research_proposal": 1.5})
    record = h.run_to_terminal()
    assert record.terminal_outcome == "failed"
    assert "timed out" in record.reason
    assert record.stage_attempts["research_proposal"] == 3
    failure_ref = record.produced_artifacts["failure_record"]
    failure = h.artifacts.get_model(FailureRecord, failure_ref.artifact_key, failure_ref.revision)
    assert failure.error_type == "timeout"


def test_build_uncertainty_loops_back_then_succeeds(tmp_path: Path) -> None:
    h = Harness(tmp_path, coding_outcomes=("blocked", "complete"))
    record = h.engine.start_run("request", user_identity="u")
    run_id = record.run_id
    h.engine.advance(run_id)
    h.engine.record_decision(run_id, "approve", user_identity="u")
    h.engine.advance(run_id)
    h.engine.record_decision(run_id, "approve", user_identity="u")
    record = h.engine.advance(run_id)
    # First build hit uncertainty: looped back to planning and paused for a NEW approval.
    assert record.state is RunState.AWAITING_DECISION
    assert record.current_stage == "plan_approval"
    assert "synchronization_result" not in record.produced_artifacts
    assert record.stage_attempts["build_execution"] == 1
    h.engine.record_decision(run_id, "approve", user_identity="u")
    record = h.engine.advance(run_id)
    assert record.state is RunState.TERMINAL
    assert record.terminal_outcome == "success"
    assert record.stage_attempts["build_execution"] == 2
    assert "def subtract" in (h.target / "src" / "calc.py").read_text(encoding="utf-8")
    types = [event.event_type for event in h.events.load(run_id)]
    assert types.count(EventType.APPROVAL_REQUESTED) == 3  # research + plan + re-approval after loopback


def test_build_not_valid_routes_failed(tmp_path: Path) -> None:
    h = Harness(tmp_path, coding_outcomes=("failed",))
    record = h.run_to_terminal()
    assert record.terminal_outcome == "failed"
    assert record.reason == "build task returned not_valid"
    assert "synchronization_result" not in record.produced_artifacts
    assert record.stage_attempts["build_execution"] == 1  # build failures route straight to completion


def test_build_loopback_exhaustion_routes_failed(tmp_path: Path) -> None:
    """Declared edge bound (D29): max_loops=2 -> builds 1,2 loop back, build 3 fails the run."""
    h = Harness(tmp_path, coding_outcomes=("blocked", "blocked", "blocked"))
    record = h.engine.start_run("request", user_identity="u")
    run_id = record.run_id
    for _ in range(4):  # research_approval, plan_approval, then plan_approval after each loopback
        record = h.engine.advance(run_id)
        assert record.state is RunState.AWAITING_DECISION
        h.engine.record_decision(run_id, "approve", user_identity="u")
    record = h.engine.advance(run_id)  # build #3: attempt 3 > max_loops 2 -> failed
    assert record.state is RunState.TERMINAL
    assert record.terminal_outcome == "failed"
    assert "loopback limit" in record.reason
    assert record.stage_attempts["build_execution"] == 3
    assert "synchronization_result" not in record.produced_artifacts
    failure_ref = record.produced_artifacts["failure_record"]
    failure = h.artifacts.get_model(FailureRecord, failure_ref.artifact_key, failure_ref.revision)
    assert failure.error_type == "uncertainty"
