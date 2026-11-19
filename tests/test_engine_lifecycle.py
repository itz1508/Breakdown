"""P2-T7a — engine lifecycle e2e: scripted run through all eight stages."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from breakdown.approvals import ApprovalManager
from breakdown.artifact_store import ArtifactStore
from breakdown.engine import EngineStores, WorkflowEngine, load_workflow
from breakdown.events import EventStore
from breakdown.models import (
    CompletionRecord,
    EventType,
    ExecutionResult,
    RunState,
    TokenUsage,
)
from breakdown.run_store import RunStore
from breakdown.safety import SafetyBoundary

REPO_ROOT = Path(__file__).resolve().parent.parent


def _now() -> datetime:
    return datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)


def _definition():  # type: ignore[no-untyped-def]
    return load_workflow(REPO_ROOT / "breakdown.yaml")


def _plan_dict() -> dict[str, Any]:
    return {
        "objective": "Answer the approved research questions",
        "input_refs": ["research_proposal"],
        "steps": ["investigate each approved question"],
        "expected_output_keys": ["research_response"],
        "completion_criteria": ["every approved question addressed"],
        "evidence_required": ["provenance for material findings"],
    }


PROPOSAL_OUTPUT: dict[str, Any] = {
    "exact_user_intent": "Add subtract to src/calc.py with a test.",
    "candidate_requirements": [
        {
            "requirement_id": "req-1",
            "text": "subtract function",
            "origin": "user",
            "coverage": "not_covered",
            "evidence": "src/calc.py defines add only",
        }
    ],
    "research_questions": [{"question_id": "q-1", "text": "Which test conventions apply?", "reason": "scope"}],
    "candidate_source_responsibilities": [
        {"requirement_refs": ["req-1"], "purpose": "implement subtract", "path": "src/calc.py"}
    ],
    "research_execution_processing_plan": _plan_dict(),
}

RESEARCH_OUTPUT: dict[str, Any] = {
    "research_record": {
        "record_id": "rr-1",
        "resolved_questions": [{"question_id": "q-1", "answer": "pytest in tests/", "evidence_refs": ["ev-1"]}],
        "unresolved_questions": [],
        "evidence": [
            {
                "evidence_id": "ev-1",
                "claim": "repo uses pytest",
                "source_identity": "target-repo",
                "source_location": "tests/test_calc.py",
                "accessed_at": "2026-11-18T00:00:00+00:00",
                "status": "supported",
            }
        ],
        "contradictions": [],
        "fixture_specifications": [],
    },
    "report_summary": "addressed",
    "research_todo": {"items": [{"question_id": "q-1", "status": "completed"}]},
}


FINDINGS_OUTPUT: dict[str, Any] = {
    "classified_findings": [
        {
            "finding_id": "f-1",
            "requirement_ref": "req-1",
            "claim": "subtract missing",
            "status": "supported",
            "decision_trace": [{"check": "inspected", "observation": "true", "evidence_ref": "ev-1"}],
            "criterion": "valid",
            "reason": "direct observation",
        }
    ],
    "normalized_evidence": [],
    "reviewed_fixture_specifications": [],
    "reviewed_unresolved_questions": [],
    "contradictions_preserved": [],
    "implementation_planning_processing_plan": {
        "objective": "Create the ImplementationPlan",
        "input_refs": ["findings_review"],
        "steps": ["produce cohesive build tasks"],
        "expected_output_keys": ["implementation_plan"],
        "completion_criteria": ["all requirements traced"],
        "evidence_required": ["reuse evidence"],
    },
}

PLAN_OUTPUT: dict[str, Any] = {
    "planning_gap_analysis": ["subtract missing"],
    "planning_gap_resolutions": ["add subtract + test"],
    "implementation_plan": {
        "plan_id": "plan-1",
        "revision": 1,
        "objective": "Add subtract with a test",
        "requirement_refs": ["req-1"],
        "source_checkpoint_ref": {"artifact_key": "source_checkpoint", "digest": "1" * 64},
        "technology_decisions": [],
        "tasks": [
            {
                "task_id": "task-1",
                "sequence": 1,
                "responsibility": "add subtract with test",
                "requirement_refs": ["req-1"],
                "target_paths": [{"path": "src/calc.py", "disposition": "modify"}],
                "source_evidence": ["f-1"],
                "capability_reuse": [],
                "reference_ids": [],
                "expected_result": "subtract(3, 2) == 1",
                "validation_steps": [
                    {
                        "step_id": "v-1",
                        "description": "run tests",
                        "command_or_observation": "pytest -q",
                        "expected": "pass",
                    }
                ],
                "required_evidence": ["test output"],
            }
        ],
        "integration_checks": [],
        "success_criteria": [{"criterion": "subtract tested", "measurable": True}],
    },
    "planning_review_result": {"cohesion": "valid", "notes": ""},
    "build_execution_processing_plan": {
        "objective": "Execute approved tasks in sandbox",
        "input_refs": ["implementation_plan"],
        "steps": ["apply tasks sequentially"],
        "expected_output_keys": ["task_results"],
        "completion_criteria": ["evidence-backed results"],
        "evidence_required": ["check observations"],
    },
}


class ScriptedRoleBackend:
    """Returns canned structured outputs keyed by operation."""

    def __init__(self, scripted: Mapping[str, Mapping[str, Any]]) -> None:
        self._scripted = dict(scripted)

    async def generate(self, request: Any) -> Any:
        from breakdown.models import RoleBackendResponse, TokenUsage

        payload = self._scripted.get(request.operation)
        if payload is None:
            raise RuntimeError(f"no scripted output for {request.operation}")
        return RoleBackendResponse(
            structured_output=payload,
            text="",
            usage=TokenUsage(input_tokens=100, output_tokens=200, tool_calls=1),
            provider="fake",
            model="fake-e2e",
        )


class _ScriptedCodingBackend:
    """Applies the approved change inside the sandbox (simulated build work)."""

    async def apply_task(self, request: Any) -> Any:
        from breakdown.models import CodingBackendResult

        sandbox = Path(request.sandbox_root)
        (sandbox / "src" / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
            encoding="utf-8",
        )
        return CodingBackendResult(
            execution_result=ExecutionResult.COMPLETED,
            observation="subtract implemented in sandbox",
            reported_changed_paths=("src/calc.py",),
            usage=TokenUsage(input_tokens=40, output_tokens=60, tool_calls=2),
        )


class _E2E:
    """Target repo + stores + engine wired with scripted fakes."""

    def __init__(self, tmp_path: Path) -> None:
        self.target = tmp_path / "repo"
        (self.target / "src").mkdir(parents=True)
        (self.target / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        state = tmp_path / "state"
        self.artifacts = ArtifactStore(state)
        self.events = EventStore(state)
        self.runs = RunStore(state)
        self.safety = SafetyBoundary(target_root=self.target, state_root=state)
        self.definition = _definition()
        from breakdown.contracts import build_contract_registry
        from breakdown.roles import RoleToolkit
        from breakdown.roles.auditor import Auditor
        from breakdown.roles.builder import Builder
        from breakdown.roles.planner import Planner
        from breakdown.roles.researcher import Researcher

        self.contracts = build_contract_registry(self.definition)
        self.approvals = ApprovalManager(
            artifacts=self.artifacts, events=self.events, runs=self.runs, definition=self.definition
        )
        self.backend = ScriptedRoleBackend(
            {
                "create_research_proposal": PROPOSAL_OUTPUT,
                "execute_research": RESEARCH_OUTPUT,
                "review_research_findings": FINDINGS_OUTPUT,
                "create_implementation_plan": PLAN_OUTPUT,
            }
        )

        def role_factory(sandbox: Path | None) -> Mapping[str, object]:
            return {
                "auditor": Auditor(backend=self.backend, tools=RoleToolkit(role="auditor", root=self.target)),
                "researcher": Researcher(backend=self.backend, tools=RoleToolkit(role="researcher", root=self.target)),
                "planner": Planner(backend=self.backend, tools=RoleToolkit(role="planner", root=self.target)),
                "builder": Builder(backend=_ScriptedCodingBackend(), sandbox_root=sandbox or self.target),
            }

        self.engine = WorkflowEngine(
            definition=self.definition,
            contracts=self.contracts,
            stores=EngineStores(artifacts=self.artifacts, events=self.events, runs=self.runs, safety=self.safety),
            approvals=self.approvals,
            role_factory=role_factory,
        )


@pytest.fixture
def e2e(tmp_path: Path) -> _E2E:
    return _E2E(tmp_path)


def test_happy_path_reaches_completion_success(e2e: _E2E) -> None:
    record = e2e.engine.start_run("Add subtract to src/calc.py with a test.", user_identity="user@example.com")
    run_id = record.run_id
    assert record.definition_digest
    assert record.state is RunState.RUNNING

    record = e2e.engine.advance(run_id)
    assert record.state is RunState.AWAITING_DECISION
    assert record.current_stage == "research_approval"

    record = e2e.engine.record_decision(run_id, "approve", user_identity="user@example.com")
    assert record.state is RunState.RUNNING
    record = e2e.engine.advance(run_id)
    assert record.state is RunState.AWAITING_DECISION
    assert record.current_stage == "plan_approval"
    assert "frozen_plan" in record.produced_artifacts
    assert "preflight_result" in record.produced_artifacts

    record = e2e.engine.record_decision(run_id, "approve", user_identity="user@example.com")
    record = e2e.engine.advance(run_id)
    assert record.state is RunState.TERMINAL
    assert record.terminal_outcome == "success"

    content = (e2e.target / "src" / "calc.py").read_text(encoding="utf-8")
    assert "def subtract" in content

    completion_ref = record.produced_artifacts["completion_record"]
    completion = e2e.artifacts.get_model(CompletionRecord, completion_ref.artifact_key, completion_ref.revision)
    assert completion.completion_outcome == "success"
    assert completion.changed_paths == ("src/calc.py",)
    assert completion.terminal_state == "completed"
    # Budget counts coding-backend usage too: 4 role activations x 300 tokens
    # (100 in + 200 out, 1 call each) + builder 100 tokens (40 in + 60 out, 2 calls).
    assert record.tokens_used == 1300
    assert record.tool_calls_used == 6
    assert completion.cost_summary is not None
    assert completion.cost_summary.tokens_used == 1300


def test_event_sequence(e2e: _E2E) -> None:
    record = e2e.engine.start_run("request", user_identity="u")
    run_id = record.run_id
    e2e.engine.advance(run_id)
    e2e.engine.record_decision(run_id, "approve", user_identity="u")
    e2e.engine.advance(run_id)
    e2e.engine.record_decision(run_id, "approve", user_identity="u")
    e2e.engine.advance(run_id)
    types = [event.event_type for event in e2e.events.load(run_id)]
    assert types.count(EventType.APPROVAL_REQUESTED) == 2
    assert types.count(EventType.APPROVAL_RECORDED) == 2
    assert types.count(EventType.STAGE_ENTERED) == 7  # 5 role stages + 2 decision stages
    assert types.count(EventType.STAGE_COMPLETED) == 5  # five role stages
    assert types.count(EventType.RUN_COMPLETED) == 1
    assert types[-1] is EventType.RUN_COMPLETED
    assert EventType.ARTIFACT_PRODUCED in types


def test_cross_instance_resume(e2e: _E2E) -> None:
    record = e2e.engine.start_run("request", user_identity="u")
    run_id = record.run_id
    e2e.engine.advance(run_id)  # pauses at research_approval

    engine2 = WorkflowEngine(
        definition=e2e.definition,
        contracts=e2e.contracts,
        stores=EngineStores(artifacts=e2e.artifacts, events=e2e.events, runs=e2e.runs, safety=e2e.safety),
        approvals=ApprovalManager(artifacts=e2e.artifacts, events=e2e.events, runs=e2e.runs, definition=e2e.definition),
        role_factory=e2e.engine.role_factory,
    )
    record2 = engine2.record_decision(run_id, "approve", user_identity="u")
    assert record2.state is RunState.RUNNING
    record2 = engine2.advance(run_id)
    assert record2.state is RunState.AWAITING_DECISION
    engine2.record_decision(run_id, "approve", user_identity="u")
    final = engine2.advance(run_id)
    assert final.state is RunState.TERMINAL
    assert final.terminal_outcome == "success"


def test_cancel_mid_run(e2e: _E2E) -> None:
    record = e2e.engine.start_run("request", user_identity="u")
    e2e.engine.advance(record.run_id)
    final = e2e.engine.cancel(record.run_id, reason="user cancelled")
    assert final.state is RunState.TERMINAL
    assert final.terminal_outcome == "cancelled"
    assert "cancellation_record" in final.produced_artifacts
    assert "retained_evidence" in final.produced_artifacts


def test_start_run_pins_definition_and_checkpoint(e2e: _E2E) -> None:
    record = e2e.engine.start_run("request", user_identity="u")
    assert record.definition_version == 1
    assert record.definition_digest
    assert "source_checkpoint" in record.produced_artifacts
    assert "initial_request" in record.produced_artifacts


def test_advance_unknown_run(e2e: _E2E) -> None:
    from breakdown.engine import EngineError

    with pytest.raises(EngineError):
        e2e.engine.advance("run-ghost")
