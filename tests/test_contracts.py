"""Task 4/6 — contract tests: strict models, vocabulary separation,
registry alignment, activators, and structure rules."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from breakdown.contracts import (
    ContractActivationError,
    activate_decision_contract,
    activate_role_contract,
    build_contract_registry,
    validate_alignment,
)
from breakdown.engine import load_workflow
from breakdown.models import (
    OPERATION_IO,
    ContractKind,
    CriterionResult,
    ExecutionResult,
    ExecutionStatus,
    InitialRequest,
    RunRef,
    StageContext,
    UserDecision,
)

DEFINITION_PATH = Path(__file__).resolve().parent.parent / "breakdown.yaml"


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


def test_agents_is_data_only() -> None:
    root = Path(__file__).resolve().parent.parent
    assert not (root / "agents" / "__init__.py").exists()
    assert not list((root / "agents").rglob("__init__.py"))
    skill_dirs = sorted(path.name for path in (root / "agents" / "skills").iterdir() if path.is_dir())
    assert skill_dirs == ["auditor", "builder", "coder", "planner", "researcher"]


def test_retired_modules_absent() -> None:
    package = Path(__file__).resolve().parent.parent / "breakdown"
    for retired in ("sdk_runner.py", "hooks.py"):
        assert not (package / retired).exists(), retired
    assert not (package / "mcp").exists()
