"""P2-T5 — approvals: durable decisions, binding digests, timeouts, loops."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from breakdown.shared.models import (
    ArtifactRef,
    EventType,
    FrozenPlan,
    ImplementationPlan,
    PlanApprovalRecord,
    PreflightResult,
    ProcessingPlan,
    ResearchApprovalRecord,
    ResearchProposalOutput,
    RunRecord,
    RunState,
    SourceCheckpoint,
    WorkflowDefinition,
)
from breakdown.system.runtime.approvals import (
    ApprovalBindingStale,
    ApprovalError,
    ApprovalManager,
    DecisionNotPending,
    PLAN_LOOP_COUNTER,
)
from breakdown.system.storage.artifact_store import ArtifactStore
from breakdown.system.storage.canonical import approval_hash as compute_approval_hash
from breakdown.system.storage.canonical import frozen_plan_hash
from breakdown.system.storage.events import EventStore
from breakdown.system.storage.run_store import RunStore

REPO_ROOT = Path(__file__).resolve().parents[3]


def _now() -> datetime:
    return datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)


def _definition() -> WorkflowDefinition:
    raw = yaml.safe_load((REPO_ROOT / "breakdown.yaml").read_text(encoding="utf-8"))
    return WorkflowDefinition.model_validate(raw)


def _checkpoint() -> SourceCheckpoint:
    return SourceCheckpoint(
        repository_identity="repo", commit_sha="a" * 40, file_hashes={"src/x.py": "h"}, captured_at=_now()
    )


def _proposal() -> ResearchProposalOutput:
    return ResearchProposalOutput.model_validate(
        {
            "exact_user_intent": "intent",
            "candidate_requirements": [
                {
                    "requirement_id": "r1",
                    "text": "t",
                    "origin": "user",
                    "coverage": "covered",
                    "evidence": "e",
                }
            ],
            "research_execution_processing_plan": {
                "objective": "o",
                "input_refs": ["research_proposal"],
                "steps": ["s"],
                "expected_output_keys": ["research_response"],
                "completion_criteria": ["c"],
                "evidence_required": ["e"],
            },
        }
    )


def _plan() -> ImplementationPlan:
    return ImplementationPlan.model_validate(
        {
            "plan_id": "p1",
            "revision": 1,
            "objective": "o",
            "requirement_refs": ["r1"],
            "source_checkpoint_ref": {"artifact_key": "source_checkpoint", "digest": "d" * 64},
            "tasks": [
                {
                    "task_id": "t1",
                    "sequence": 1,
                    "responsibility": "resp",
                    "requirement_refs": ["r1"],
                    "target_paths": [{"path": "src/x.py", "disposition": "modify"}],
                    "expected_result": "ok",
                    "validation_steps": [
                        {"step_id": "v1", "description": "d", "command_or_observation": "c", "expected": "e"}
                    ],
                    "required_evidence": ["ev"],
                }
            ],
            "success_criteria": [{"criterion": "c"}],
        }
    )


def _processing_plan() -> ProcessingPlan:
    return ProcessingPlan(
        objective="o",
        input_refs=["a"],
        steps=["s"],
        expected_output_keys=["task_results"],
        completion_criteria=["c"],
        evidence_required=["e"],
    )


class _Harness:
    """Stores + run fixture positioned at a decision stage."""

    def __init__(self, tmp_path: Path, stage_id: str) -> None:
        state = tmp_path / ".breakdown"
        self.artifacts = ArtifactStore(state)
        self.events = EventStore(state)
        self.runs = RunStore(state)
        self.definition = _definition()
        self.manager = ApprovalManager(
            artifacts=self.artifacts, events=self.events, runs=self.runs, definition=self.definition
        )
        self.checkpoint = _checkpoint()
        produced: dict[str, ArtifactRef] = {
            "source_checkpoint": self.artifacts.store_artifact(
                self.checkpoint, "source_checkpoint", contract_id="runtime", contract_version="1"
            )
        }
        if stage_id in ("research_approval", "plan_approval"):
            proposal = _proposal()
            produced["research_proposal"] = self.artifacts.store_artifact(
                proposal, "research_proposal", contract_id="research_proposal", contract_version="1"
            )
            produced["research_execution_processing_plan"] = self.artifacts.store_artifact(
                proposal.research_execution_processing_plan,
                "research_execution_processing_plan",
                contract_id="research_proposal",
                contract_version="1",
            )
        if stage_id == "plan_approval":
            plan = _plan()
            produced["implementation_plan"] = self.artifacts.store_artifact(
                plan, "implementation_plan", contract_id="implementation_planning", contract_version="1"
            )
            frozen = FrozenPlan(
                plan=plan,
                frozen_plan_hash=frozen_plan_hash(plan, self.checkpoint, 1),
                source_checkpoint=self.checkpoint,
                definition_version=1,
                frozen_at=_now(),
            )
            produced["frozen_plan"] = self.artifacts.store_artifact(
                frozen, "frozen_plan", contract_id="implementation_planning", contract_version="1"
            )
            produced["preflight_result"] = self.artifacts.store_artifact(
                PreflightResult(
                    criterion="valid",
                    criteria_results=({"name": "n", "criterion": "valid", "evidence": "e"},),
                    checked_at=_now(),
                ),
                "preflight_result",
                contract_id="implementation_planning",
                contract_version="1",
            )
            produced["build_execution_processing_plan"] = self.artifacts.store_artifact(
                _processing_plan(),
                "build_execution_processing_plan",
                contract_id="implementation_planning",
                contract_version="1",
            )
        self.record = RunRecord(
            run_id="run-1",
            session_id="s-1",
            workflow_id="oneshot.breakdown",
            definition_version=1,
            definition_digest="0" * 64,
            state=RunState.RUNNING,
            current_stage=stage_id,
            produced_artifacts=produced,
            created_at=_now(),
            updated_at=_now(),
        )
        self.runs.create_run(self.record)

    def revision(self) -> int:
        loaded = self.runs.load("run-1")
        assert loaded is not None
        return loaded[0]

    def current(self) -> RunRecord:
        loaded = self.runs.load("run-1")
        assert loaded is not None
        return loaded[1]


@pytest.fixture
def research_harness(tmp_path: Path) -> _Harness:
    return _Harness(tmp_path, "research_approval")


@pytest.fixture
def plan_harness(tmp_path: Path) -> _Harness:
    return _Harness(tmp_path, "plan_approval")


def test_request_decision_persists_pending_and_pauses(research_harness: _Harness) -> None:
    h = research_harness
    pending = h.manager.request_decision("run-1")
    assert pending.stage_id == "research_approval"
    assert pending.options == ("approve", "cancel")
    assert set(pending.binding_refs) == {
        "research_proposal",
        "research_execution_processing_plan",
        "source_checkpoint",
    }
    record = h.current()
    assert record.state is RunState.AWAITING_DECISION
    events = h.events.load("run-1")
    assert events[-1].event_type is EventType.APPROVAL_REQUESTED


def test_request_decision_requires_decision_stage(research_harness: _Harness) -> None:
    h = research_harness
    h.runs.update_run(
        h.current().model_copy(update={"current_stage": "research_execution"}),
        expected_revision=h.revision(),
    )
    with pytest.raises(ApprovalError):
        h.manager.request_decision("run-1")


def test_request_decision_missing_binding(research_harness: _Harness) -> None:
    h = research_harness
    produced = dict(h.current().produced_artifacts)
    del produced["research_proposal"]
    h.runs.update_run(
        h.current().model_copy(update={"produced_artifacts": produced}),
        expected_revision=h.revision(),
    )
    with pytest.raises(ApprovalError):
        h.manager.request_decision("run-1")


def test_research_approve_persists_record_and_advances(research_harness: _Harness) -> None:
    h = research_harness
    h.manager.request_decision("run-1")
    outcome = h.manager.record_decision("run-1", "approve", user_identity="user@example.com")
    assert outcome.target_stage == "research_execution"
    assert outcome.terminal is False
    record = h.current()
    assert record.state is RunState.RUNNING
    ref = record.produced_artifacts["research_approval_record"]
    stored = h.artifacts.get_model(ResearchApprovalRecord, ref.artifact_key, ref.revision)
    assert stored.decision.action == "approve"
    assert stored.decision.user_identity == "user@example.com"
    assert stored.research_proposal_digest == h.record.produced_artifacts["research_proposal"].digest


def test_research_cancel_routes_to_completion(research_harness: _Harness) -> None:
    h = research_harness
    h.manager.request_decision("run-1")
    outcome = h.manager.record_decision("run-1", "cancel", user_identity="u", reason="not needed")
    assert outcome.terminal is True
    assert outcome.terminal_outcome == "cancelled"
    assert outcome.target_stage == "completion"
    assert "cancellation_record" in outcome.produced


def test_unknown_action_rejected(research_harness: _Harness) -> None:
    h = research_harness
    h.manager.request_decision("run-1")
    with pytest.raises(ApprovalError):
        h.manager.record_decision("run-1", "decline", user_identity="u")


def test_decision_without_pending_rejected(research_harness: _Harness) -> None:
    with pytest.raises(DecisionNotPending):
        research_harness.manager.record_decision("run-1", "approve", user_identity="u")


def test_stale_binding_rejected(plan_harness: _Harness) -> None:
    h = plan_harness
    h.manager.request_decision("run-1")
    # A new frozen_plan revision lands after the pause -> binding drift.
    frozen_ref = h.current().produced_artifacts["frozen_plan"]
    frozen = h.artifacts.get_model(FrozenPlan, frozen_ref.artifact_key, frozen_ref.revision)
    drifted = frozen.model_copy(update={"definition_version": 2})
    new_ref = h.artifacts.store_artifact(
        drifted, "frozen_plan", contract_id="implementation_planning", contract_version="1"
    )
    produced = dict(h.current().produced_artifacts)
    produced["frozen_plan"] = new_ref
    h.runs.update_run(
        h.current().model_copy(update={"produced_artifacts": produced}),
        expected_revision=h.revision(),
    )
    with pytest.raises(ApprovalBindingStale):
        h.manager.record_decision("run-1", "approve", user_identity="u")


def test_plan_approve_hash_verifies(plan_harness: _Harness) -> None:
    h = plan_harness
    h.manager.request_decision("run-1")
    outcome = h.manager.record_decision("run-1", "approve", user_identity="user@example.com")
    assert outcome.target_stage == "build_execution"
    record = h.current()
    ref = record.produced_artifacts["plan_approval_record"]
    stored = h.artifacts.get_model(PlanApprovalRecord, ref.artifact_key, ref.revision)
    frozen_ref = record.produced_artifacts["frozen_plan"]
    frozen = h.artifacts.get_model(FrozenPlan, frozen_ref.artifact_key, frozen_ref.revision)
    expected = compute_approval_hash(frozen.frozen_plan_hash, frozen.source_checkpoint, stored.decision)
    assert stored.approval_hash == expected
    assert "approved_plan_revision" in record.produced_artifacts
    assert "approved_source_checkpoint" in record.produced_artifacts


def test_plan_decline_routes_cancelled(plan_harness: _Harness) -> None:
    h = plan_harness
    h.manager.request_decision("run-1")
    outcome = h.manager.record_decision("run-1", "decline", user_identity="u", reason="too risky")
    assert outcome.terminal is True
    assert outcome.terminal_outcome == "cancelled"
    assert "cancellation_record" in outcome.produced


def test_plan_request_changes_increments_loop(plan_harness: _Harness) -> None:
    h = plan_harness
    h.manager.request_decision("run-1")
    outcome = h.manager.record_decision("run-1", "request_changes", user_identity="u", reason="adjust scope")
    assert outcome.target_stage == "implementation_planning"
    assert outcome.terminal is False
    assert outcome.loop_counter == 1
    assert "frozen_plan" in outcome.invalidated_keys
    record = h.current()
    assert record.loop_counters[PLAN_LOOP_COUNTER] == 1
    events = h.events.load("run-1")
    assert "invalidated" in events[-1].payload


def test_plan_loop_exhaustion_routes_failed(plan_harness: _Harness) -> None:
    h = plan_harness
    h.runs.update_run(
        h.current().model_copy(update={"loop_counters": {PLAN_LOOP_COUNTER: 3}}),
        expected_revision=h.revision(),
    )
    h.manager.request_decision("run-1")
    outcome = h.manager.record_decision("run-1", "request_changes", user_identity="u")
    assert outcome.terminal is True
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason == "loop_exhausted"
    assert outcome.target_stage == "completion"


def test_timeout_routes_cancelled(plan_harness: _Harness) -> None:
    h = plan_harness
    h.manager.request_decision("run-1")
    late = datetime(2027, 1, 1, tzinfo=UTC)  # well beyond the 86400s timeout
    outcome = h.manager.record_decision("run-1", "approve", user_identity="u", decided_at=late)
    assert outcome.action == "timeout"
    assert outcome.terminal is True
    assert outcome.terminal_outcome == "cancelled"
    assert outcome.reason == "timeout"


def test_double_decision_rejected(plan_harness: _Harness) -> None:
    h = plan_harness
    h.manager.request_decision("run-1")
    h.manager.record_decision("run-1", "approve", user_identity="u")
    with pytest.raises(DecisionNotPending):
        h.manager.record_decision("run-1", "approve", user_identity="u")
