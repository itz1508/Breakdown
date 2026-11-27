"""Task 4/6 — contract tests: strict models, vocabulary separation,
registry alignment, activators, and structure rules."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from breakdown.shared.models import (
    BuildExecutionOutput,
    ContractKind,
    CriterionResult,
    ExecutionResult,
    ExecutionStatus,
    FindingsReviewOutput,
    ImplementationPlanningOutput,
    InitialRequest,
    OPERATION_IO,
    ResearchExecutionOutput,
    ResearchProposalOutput,
    RunRef,
    StageContext,
    UserDecision,
)
from breakdown.system.runtime.contracts import (
    activate_decision_contract,
    activate_role_contract,
    build_contract_registry,
    ContractActivationError,
    mapped_output_keys,
    RUNTIME_OWNED_KEYS,
    validate_alignment,
)
from breakdown.system.runtime.engine import load_workflow

DEFINITION_PATH = Path(__file__).resolve().parents[2] / "breakdown.yaml"


def utcnow() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(scope="module")
def definition():  # type: ignore[no-untyped-def]
    return load_workflow(DEFINITION_PATH)


@pytest.fixture(scope="module")
def registry(definition):  # type: ignore[no-untyped-def]
    return build_contract_registry(definition)


def _context(stage_id: str) -> StageContext:
    return StageContext(
        run=RunRef(run_id="run-1", session_id="s-1", definition_version=1, definition_digest="0" * 64),
        stage_id=stage_id,
    )


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        InitialRequest.model_validate({"text": "x", "created_at": utcnow().isoformat(), "extra": 1})


def test_lifecycle_failed_is_distinct_from_criterion_not_valid() -> None:
    assert "failed" not in {member.value for member in CriterionResult}
    assert ExecutionResult.FAILED.value == "failed"
    assert CriterionResult.NOT_VALID.value == "not_valid"


def test_execution_status_matches_definition_vocabulary(definition: Any) -> None:
    declared = set(definition.vocabularies["execution_status"])
    assert declared == {member.value for member in ExecutionStatus}


def test_registry_alignment_eight_to_eight(definition: Any, registry: Any) -> None:
    assert len(registry) == 8
    validate_alignment(registry, definition)


def test_kind_distribution(definition: Any) -> None:
    kinds = [stage.kind for stage in definition.stages]
    assert kinds.count(ContractKind.ROLE) == 5
    assert kinds.count(ContractKind.DECISION) == 2
    assert kinds.count(ContractKind.DETERMINISTIC) == 1


def test_every_role_stage_has_typed_io(definition: Any, registry: Any) -> None:
    for stage in definition.stages:
        if stage.kind is ContractKind.ROLE:
            assert stage.operation in OPERATION_IO, stage.id
            contract = registry.get(stage.id)
            assert contract.input_model is not None
            assert contract.output_model is not None
            if len(contract.produces) > 1:
                assert contract.output_mapper is not None, f"{stage.id} needs an explicit output_mapper"


def test_decision_contracts_carry_declared_options(registry: Any) -> None:
    assert registry.get("research_approval").options == ("approve", "cancel")
    assert registry.get("plan_approval").options == ("approve", "request_changes", "decline")


def test_decision_activation_rejects_wrong_stage_and_action(registry: Any) -> None:
    contract = registry.get("research_approval")
    wrong_stage = UserDecision(
        stage_id="plan_approval",
        action="approve",
        run_id="r",
        session_id="s",
        user_identity="u",
        decided_at=utcnow(),
    )
    with pytest.raises(ContractActivationError):
        activate_decision_contract(contract, wrong_stage, _context("research_approval"))
    bad_action = UserDecision(
        stage_id="research_approval",
        action="decline",
        run_id="r",
        session_id="s",
        user_identity="u",
        decided_at=utcnow(),
    )
    with pytest.raises(ContractActivationError):
        activate_decision_contract(contract, bad_action, _context("research_approval"))


def test_decision_activation_accepts_declared_action(registry: Any) -> None:
    contract = registry.get("research_approval")
    decision = UserDecision(
        stage_id="research_approval",
        action="approve",
        run_id="r",
        session_id="s",
        user_identity="u",
        decided_at=utcnow(),
    )
    result = activate_decision_contract(contract, decision, _context("research_approval"))
    assert result.criterion is CriterionResult.VALID


async def test_role_activation_rejects_invalid_input(registry: Any) -> None:
    contract = registry.get("research_proposal")

    class _Role:
        async def create_research_proposal(self, input_value: Any, context: Any) -> Any:
            raise AssertionError("operation must not run on invalid input")

    with pytest.raises(ContractActivationError):
        await activate_role_contract(contract, {}, _context("research_proposal"), {"auditor": _Role()})


async def test_role_activation_requires_registered_role(registry: Any) -> None:
    contract = registry.get("research_proposal")
    with pytest.raises(ContractActivationError):
        await activate_role_contract(
            contract,
            {"initial_request": {"text": "x", "created_at": utcnow().isoformat()}},
            _context("research_proposal"),
            {},
        )


def test_multi_output_contract_requires_mapper_flag(definition: Any, registry: Any) -> None:
    # Every role stage with multiple produced keys carries an explicit mapper,
    # so no artifact mapping is ever inferred.
    for stage in definition.stages:
        contract = registry.get(stage.id)
        if contract.kind is ContractKind.ROLE and len(contract.produces) > 1:
            assert contract.output_mapper is not None


def test_agent_skills_are_colocated_with_packages() -> None:
    root = Path(__file__).resolve().parents[2]
    package = root / "breakdown"
    assert not (root / "agents").exists()
    skill_paths = (
        package / "researcher" / "SKILL.md",
        package / "auditor" / "SKILL.md",
        package / "coder" / "SKILL.md",
        package / "planner" / "SKILL.md",
        package / "builder" / "SKILL.md,
    )
    assert all(path.is_file() for path in skill_paths)


def test_retired_modules_absent() -> None:
    package = Path(__file__).resolve().parents[1]
    for retired in ("sdk_runner.py", "hooks.py"):
        assert not (package / retired).exists(), retired
    assert not (package / "mcp").exists()
    assert not (package / "roles").exists()


# --- F2: produces-coverage invariant and mapper drift guard ---


def _plan_payload(expected: tuple[str, ...] = ("research_response",)) -> dict[str, Any]:
    return {
        "objective": "o",
        "input_refs": ["research_proposal"],
        "steps": ["s"],
        "expected_output_keys": list(expected),
        "completion_criteria": ["c"],
        "evidence_required": ["e"],
    }


def _valid_output_instances() -> dict[str, Any]:
    proposal = ResearchProposalOutput(
        exact_user_intent="x",
        candidate_requirements=(
            {
                "requirement_id": "r1",
                "text": "t",
                "origin": "user",
                "coverage": "covered",
                "evidence": "e",
            },
        ),
        research_execution_processing_plan=_plan_payload(),
    )
    research = ResearchExecutionOutput(
        research_record={
            "record_id": "rr",
            "resolved_questions": ({"question_id": "q1", "answer": "a", "evidence_refs": ("e1",)},),
        },
        report_summary="s",
        research_todo={"items": ({"question_id": "q1", "status": "completed"},)},
    )
    findings = FindingsReviewOutput(
        classified_findings=(
            {
                "finding_id": "f1",
                "requirement_ref": "r1",
                "claim": "c",
                "status": "supported",
                "decision_trace": ({"check": "k", "observation": "true"},),
                "criterion": "valid",
                "reason": "r",
            },
        ),
        implementation_planning_processing_plan=_plan_payload(("implementation_plan",)),
    )
    planning = ImplementationPlanningOutput(
        implementation_plan={
            "plan_id": "p1",
            "revision": 1,
            "objective": "o",
            "requirement_refs": ("r1",),
            "source_checkpoint_ref": {"artifact_key": "source_checkpoint", "digest": "d" * 64},
            "tasks": (
                {
                    "task_id": "t1",
                    "sequence": 1,
                    "responsibility": "resp",
                    "requirement_refs": ("r1",),
                    "target_paths": ({"path": "src/x.py", "disposition": "modify"},),
                    "expected_result": "ok",
                    "validation_steps": (
                        {
                            "step_id": "v1",
                            "description": "d",
                            "command_or_observation": "c",
                            "expected": "e",
                        },
                    ),
                    "required_evidence": ("ev",),
                },
            ),
            "success_criteria": ({"criterion": "c"},),
        },
        planning_review_result={"cohesion": "valid"},
        build_execution_processing_plan=_plan_payload(("task_results",)),
    )
    build = BuildExecutionOutput(
        task_results=(
            {
                "task_id": "t1",
                "sequence": 1,
                "criterion": "valid",
                "execution_result": "completed",
                "expected": "ok",
                "actual_observation": "ok",
            },
        ),
    )
    return {
        "research_proposal": proposal,
        "research_execution": research,
        "findings_review": findings,
        "implementation_planning": planning,
        "build_execution": build,
    }


def test_produces_coverage_invariant(definition: Any) -> None:
    """Every role-stage produces key is covered by a mapper, a declared
    runtime step, or the runtime-owned registry — nothing is unproduced."""
    for stage in definition.stages:
        if stage.kind is not ContractKind.ROLE:
            continue
        step_outputs = {str(key) for step in stage.runtime_steps for key in step.get("outputs", [])}
        covered = mapped_output_keys(stage.id) | step_outputs | set(RUNTIME_OWNED_KEYS)
        uncovered = set(stage.produces) - covered
        assert not uncovered, f"{stage.id}: uncovered produces keys {sorted(uncovered)}"


def test_mapper_key_declarations_match_behavior(registry: Any) -> None:
    """Declared mapper key sets cannot drift from actual mapper output."""
    for stage_id, instance in _valid_output_instances().items():
        contract = registry.get(stage_id)
        assert contract.output_mapper is not None, stage_id
        assert set(contract.output_mapper(instance)) == mapped_output_keys(stage_id), stage_id


async def test_plan_coverage_validator_rejects_unknown_expected_keys(registry: Any) -> None:
    contract = registry.get("research_proposal")
    bad_plan = _plan_payload(("bogus_key_not_produced_by_destination",))

    class _Role:
        async def create_research_proposal(self, input_value: Any, context: Any) -> Any:
            return {
                "exact_user_intent": "x",
                "candidate_requirements": [
                    {
                        "requirement_id": "r1",
                        "text": "t",
                        "origin": "user",
                        "coverage": "covered",
                        "evidence": "e",
                    }
                ],
                "research_questions": [],
                "candidate_source_responsibilities": [],
                "research_execution_processing_plan": bad_plan,
            }

    payload = {"initial_request": {"text": "x", "created_at": utcnow().isoformat()}}
    with pytest.raises(ContractActivationError):
        await activate_role_contract(contract, payload, _context("research_proposal"), {"auditor": _Role()})
