"""Stage contracts: the activation boundary between workflow and roles.

``breakdown.yaml`` declares stage order, kinds, owners, operations,
transitions, and logical artifacts. This module never redeclares those
facts: ``build_contract_registry`` is a generator that derives
requires/produces/owner/operation from the validated definition and
attaches typed models, activators, semantic validators, and explicit
output mappers.

Authority split:

- breakdown.yaml = stage order, kinds, owners, transitions, logical artifacts
- contracts.py   = typed input/output models, activation, semantic validation
- bindings.py    = approved role implementation for each role

Backend protocols and cross-agent I/O models are owned by
:mod:`breakdown.shared.models`. This module owns runtime activation and
registry mechanics, keeping agents independent of engine and host details.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from breakdown.shared.models import (
    BuildExecutionOutput,
    ContractKind,
    FindingsReviewOutput,
    ImplementationPlanningOutput,
    OPERATION_IO,
    ResearchExecutionOutput,
    ResearchProposalOutput,
    StageContext,
    StageDefinition,
    StageResult,
    UserDecision,
    WorkflowDefinition,
)
from breakdown.system import safety

SemanticValidator = Callable[[BaseModel, StageContext], None]
OutputMapper = Callable[[Any], Mapping[str, Any]]
DeterministicOperation = Callable[[Mapping[str, Any], StageContext], Mapping[str, Any]]


class ContractError(RuntimeError):
    """Base class for contract failures."""


class ContractConfigurationError(ContractError):
    """The registry or a contract is misconfigured (build-time fault)."""


class ContractActivationError(ContractError):
    """A contract cannot activate (invalid inputs, missing binding, wrong stage)."""



@dataclass(frozen=True, slots=True)
class StageContract:
    stage_id: str
    kind: ContractKind
    owner: str
    operation: str
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    input_model: type[BaseModel] | None
    output_model: type[BaseModel] | None
    semantic_validators: tuple[SemanticValidator, ...] = ()
    output_mapper: OutputMapper | None = None
    options: tuple[str, ...] = ()


async def activate_role_contract(
    contract: StageContract,
    payload: Mapping[str, Any] | BaseModel,
    context: StageContext,
    roles: Mapping[str, Any],
) -> StageResult:
    """Validate input, invoke the role operation, validate output, run
    semantic validators, and map produced artifacts explicitly."""
    if contract.input_model is None or contract.output_model is None:
        raise ContractConfigurationError(f"{contract.stage_id}: role contract missing typed models")
    if isinstance(payload, BaseModel):
        if not isinstance(payload, contract.input_model):
            raise ContractActivationError(
                f"{contract.stage_id}: payload type {type(payload).__name__} "
                f"does not match {contract.input_model.__name__}"
            )
        input_value = payload
    else:
        try:
            input_value = contract.input_model.model_validate(dict(payload))
        except ValidationError as exc:
            raise ContractActivationError(f"{contract.stage_id}: invalid input: {exc}") from exc

    role = roles.get(contract.owner)
    if role is None:
        raise ContractActivationError(f"{contract.stage_id}: no implementation registered for role {contract.owner!r}")
    operation = getattr(role, contract.operation, None)
    if operation is None:
        raise ContractActivationError(
            f"{contract.stage_id}: role {contract.owner!r} lacks operation {contract.operation!r}"
        )

    raw_output = await operation(input_value, context)
    if isinstance(raw_output, BaseModel):
        raw_output = raw_output.model_dump(mode="python")
    try:
        output = contract.output_model.model_validate(raw_output)
    except ValidationError as exc:
        raise ContractActivationError(f"{contract.stage_id}: invalid output rejected: {exc}") from exc

    for validator in contract.semantic_validators:
        validator(output, context)

    if len(contract.produces) == 1 and contract.output_mapper is None:
        return StageResult.valid(contract.stage_id, produces={contract.produces[0]: output})
    if contract.output_mapper is None:
        raise ContractConfigurationError(f"{contract.stage_id} requires an explicit output_mapper")
    return StageResult.valid(contract.stage_id, produces=dict(contract.output_mapper(output)))


def activate_decision_contract(
    contract: StageContract,
    decision: UserDecision,
    context: StageContext,
) -> StageResult:
    """Phase 1 decision activation: pure validation, no persistence.

    Validates that the decision is addressed to this stage and uses a
    declared action. Durable persistence of approval records and the
    awaiting_decision pause are engine responsibilities (Phase 2).
    Chat text never reaches this function as a UserDecision.
    """
    if decision.stage_id != contract.stage_id:
        raise ContractActivationError(
            f"decision addressed to {decision.stage_id!r} but current stage is {contract.stage_id!r}"
        )
    if decision.action not in contract.options:
        raise ContractActivationError(
            f"{contract.stage_id}: action {decision.action!r} not in declared options {list(contract.options)}"
        )
    return StageResult.valid(contract.stage_id, produces={"decision": decision})


def activate_deterministic_contract(
    contract: StageContract,
    payload: Mapping[str, Any],
    context: StageContext,
    operations: Mapping[str, DeterministicOperation],
) -> StageResult:
    """Deterministic activation: no model is ever invoked here."""
    operation = operations.get(contract.operation)
    if operation is None:
        raise ContractActivationError(
            f"{contract.stage_id}: deterministic operation {contract.operation!r} is not wired"
        )
    produced = operation(dict(payload), context)
    return StageResult.valid(contract.stage_id, produces=dict(produced))


# --- Explicit output mappers (role-owned artifact keys only) ---
# Runtime-owned keys (source_checkpoint, *_report, *_processing_plan,
# frozen_plan, frozen_plan_hash, preflight_result, synchronization_result,
# resulting_source_checkpoint) are produced by deterministic engine steps
# in Phase 2 and are deliberately absent from these mappers.


def _research_proposal_outputs(output: ResearchProposalOutput) -> Mapping[str, Any]:
    return {
        "exact_user_intent": output.exact_user_intent,
        "candidate_requirements": output.candidate_requirements,
        "capability_coverage": tuple(
            {
                "requirement_id": requirement.requirement_id,
                "coverage": requirement.coverage.value,
                "evidence": requirement.evidence,
            }
            for requirement in output.candidate_requirements
        ),
        "research_questions": output.research_questions,
        "candidate_source_responsibilities": output.candidate_source_responsibilities,
        "research_proposal": output,
        "research_execution_processing_plan": output.research_execution_processing_plan,
    }


def _research_execution_outputs(output: ResearchExecutionOutput) -> Mapping[str, Any]:
    record = output.research_record
    return {
        "research_response": record,
        "research_todo": output.research_todo,
        "evidence_references": record.evidence,
        "fixture_specifications": record.fixture_specifications,
        "resolved_questions": record.resolved_questions,
        "unresolved_questions": record.unresolved_questions,
    }


def _findings_review_outputs(output: FindingsReviewOutput) -> Mapping[str, Any]:
    return {
        "classified_findings": output.classified_findings,
        "normalized_evidence": output.normalized_evidence,
        "reviewed_fixture_specifications": output.reviewed_fixture_specifications,
        "reviewed_unresolved_questions": output.reviewed_unresolved_questions,
        "findings_review": output,
        "implementation_planning_processing_plan": output.implementation_planning_processing_plan,
    }


def _implementation_planning_outputs(output: ImplementationPlanningOutput) -> Mapping[str, Any]:
    return {
        "planning_gap_analysis": output.planning_gap_analysis,
        "planning_gap_resolutions": output.planning_gap_resolutions,
        "implementation_plan": output.implementation_plan,
        "planning_review_result": output.planning_review_result,
        "build_execution_processing_plan": output.build_execution_processing_plan,
    }


def _build_execution_outputs(output: BuildExecutionOutput) -> Mapping[str, Any]:
    return {
        "task_results": output.task_results,
        "applied_changes": output.applied_changes,
        "validation_results": output.validation_results,
        "build_result": output,
        "execution_evidence": output.execution_evidence_refs,
    }


_OUTPUT_MAPPERS: Mapping[str, OutputMapper] = {
    "research_proposal": _research_proposal_outputs,
    "research_execution": _research_execution_outputs,
    "findings_review": _findings_review_outputs,
    "implementation_planning": _implementation_planning_outputs,
    "build_execution": _build_execution_outputs,
}


# Declared key sets of the mappers above. A contract test asserts each set
# equals the keys actually produced by its mapper on a valid output instance,
# so these declarations cannot drift from mapper behavior.
_OUTPUT_MAPPING_KEYS: Mapping[str, frozenset[str]] = {
    "research_proposal": frozenset(
        {
            "exact_user_intent",
            "candidate_requirements",
            "capability_coverage",
            "research_questions",
            "candidate_source_responsibilities",
            "research_proposal",
            "research_execution_processing_plan",
        }
    ),
    "research_execution": frozenset(
        {
            "research_response",
            "research_todo",
            "evidence_references",
            "fixture_specifications",
            "resolved_questions",
            "unresolved_questions",
        }
    ),
    "findings_review": frozenset(
        {
            "classified_findings",
            "normalized_evidence",
            "reviewed_fixture_specifications",
            "reviewed_unresolved_questions",
            "findings_review",
            "implementation_planning_processing_plan",
        }
    ),
    "implementation_planning": frozenset(
        {
            "planning_gap_analysis",
            "planning_gap_resolutions",
            "implementation_plan",
            "planning_review_result",
            "build_execution_processing_plan",
        }
    ),
    "build_execution": frozenset(
        {
            "task_results",
            "applied_changes",
            "validation_results",
            "build_result",
            "execution_evidence",
        }
    ),
}


def mapped_output_keys(stage_id: str) -> frozenset[str]:
    """Declared mapper key set for a role stage (empty for non-role stages)."""
    return _OUTPUT_MAPPING_KEYS.get(stage_id, frozenset())


# Artifact keys produced by deterministic runtime operations — never by role
# mappers: checkpoints, frozen packages, markdown projections, synchronization
# records. Values name the owning deterministic mechanism.
RUNTIME_OWNED_KEYS: Mapping[str, str] = {
    "source_checkpoint": "deterministic checkpoint operation (Phase 2 checkpoint.py)",
    "research_proposal_report": "markdown projection rendered by runtime from JSON records",
    "research_request": "runtime bookkeeping derived from proposal + processing plan",
    "research_report": "markdown projection rendered by runtime from JSON records",
    "findings_review_report": "markdown projection rendered by runtime from JSON records",
    "frozen_plan": "runtime step freeze_plan (implementation_planning.runtime_steps)",
    "frozen_plan_hash": "runtime step freeze_plan (implementation_planning.runtime_steps)",
    "preflight_result": "runtime step preflight_check (implementation_planning.runtime_steps)",
    "independent_verification": "Host-invoked independent build verifier (Phase 3b verification.py)",
    "synchronization_result": "runtime synchronization authorization (Phase 2 safety.py)",
    "resulting_source_checkpoint": "deterministic post-sync checkpoint (Phase 2 checkpoint.py)",
}


@dataclass(frozen=True, slots=True)
class ContractRegistry:
    contracts: Mapping[str, StageContract]
    definition_version: int

    def get(self, stage_id: str) -> StageContract:
        contract = self.contracts.get(stage_id)
        if contract is None:
            raise ContractConfigurationError(f"no contract registered for stage {stage_id!r}")
        return contract

    def __len__(self) -> int:
        return len(self.contracts)


def _plan_coverage_validator(plan_field: str, destination_stage: StageDefinition) -> SemanticValidator:
    """An authored processing plan may only expect outputs the destination
    stage is declared to produce (definition-derived; nothing redeclared)."""
    allowed = frozenset(destination_stage.produces)

    def _validate(output: BaseModel, context: StageContext) -> None:
        plan = getattr(output, plan_field, None)
        if plan is None:
            raise ContractActivationError(f"authored processing plan field {plan_field!r} is missing")
        unknown = set(plan.expected_output_keys) - allowed
        if unknown:
            raise ContractActivationError(
                f"{plan_field}: expected_output_keys not produced by {destination_stage.id!r}: {sorted(unknown)}"
            )

    return _validate


def build_contract_registry(
    definition: WorkflowDefinition,
    *,
    semantic_validators: Mapping[str, tuple[SemanticValidator, ...]] | None = None,
) -> ContractRegistry:
    """Derive one StageContract per declared stage.

    Requires/produces/owner/operation come from the definition only;
    this generator never redeclares workflow facts.
    """
    contracts: dict[str, StageContract] = {}
    validators = semantic_validators or {}
    for stage in definition.stages:
        if stage.id in contracts:
            raise ContractConfigurationError(f"duplicate stage id {stage.id!r}")
        kind = ContractKind(stage.kind)
        if kind is ContractKind.ROLE:
            io = OPERATION_IO.get(stage.operation)
            if io is None:
                raise ContractConfigurationError(f"no typed models registered for operation {stage.operation!r}")
            input_model, output_model = io
            stage_validators = list(validators.get(stage.id, ()))
            creates = stage.creates_processing_plan
            if creates:
                plan_name = creates.get("name")
                destination_id = creates.get("destination_stage")
                if not isinstance(plan_name, str) or not isinstance(destination_id, str):
                    raise ContractConfigurationError(
                        f"{stage.id}: creates_processing_plan must declare name and destination_stage"
                    )
                try:
                    destination_stage = definition.get_stage(destination_id)
                except KeyError as exc:
                    raise ContractConfigurationError(
                        f"{stage.id}: creates_processing_plan destination {destination_id!r} does not exist"
                    ) from exc
                stage_validators.append(_plan_coverage_validator(plan_name, destination_stage))
            contracts[stage.id] = StageContract(
                stage_id=stage.id,
                kind=kind,
                owner=stage.owner,
                operation=stage.operation,
                requires=tuple(stage.requires),
                produces=tuple(stage.produces),
                input_model=input_model,
                output_model=output_model,
                semantic_validators=tuple(stage_validators),
                output_mapper=_OUTPUT_MAPPERS.get(stage.id),
            )
        elif kind is ContractKind.DECISION:
            if not stage.options:
                raise ContractConfigurationError(f"decision stage {stage.id!r} must declare options")
            contracts[stage.id] = StageContract(
                stage_id=stage.id,
                kind=kind,
                owner=stage.owner,
                operation=stage.operation,
                requires=tuple(stage.requires),
                produces=tuple(stage.produces),
                input_model=None,
                output_model=None,
                options=tuple(stage.options),
            )
        else:
            contracts[stage.id] = StageContract(
                stage_id=stage.id,
                kind=kind,
                owner=stage.owner,
                operation=stage.operation,
                requires=tuple(stage.requires),
                produces=tuple(stage.produces),
                input_model=None,
                output_model=None,
            )
    return ContractRegistry(contracts=contracts, definition_version=definition.definition_version)


def validate_alignment(registry: ContractRegistry, definition: WorkflowDefinition) -> None:
    """Registry-definition alignment: counts, owners, operations, kinds, artifacts."""
    if len(registry) != len(definition.stages):
        raise ContractConfigurationError("contract count does not match stage count")
    for stage in definition.stages:
        contract = registry.get(stage.id)
        if contract.owner != stage.owner:
            raise ContractConfigurationError(f"{stage.id}: owner mismatch")
        if contract.operation != stage.operation:
            raise ContractConfigurationError(f"{stage.id}: operation mismatch")
        if contract.kind is not ContractKind(stage.kind):
            raise ContractConfigurationError(f"{stage.id}: kind mismatch")
        if contract.requires != tuple(stage.requires) or contract.produces != tuple(stage.produces):
            raise ContractConfigurationError(f"{stage.id}: requires/produces diverged from definition")


def validate_definition_consistency(definition: WorkflowDefinition) -> None:
    """Pin declarative mirror blocks against their runtime implementations.

    The definition declares vocabularies, the persistent-event catalog,
    ownership, authorization checks, synchronization requirements, digest
    policy, budget-exceeded policy, and the approved-package loopback
    target; the runtime implements them. Any drift between the declaration
    and the implementation is a configuration error.
    """
    from breakdown.system.storage import canonical
    from breakdown.shared.models import (
        CapabilityCoverage,
        CriterionResult,
        EventPersistence,
        EventType,
        ExecutionStatus,
    )

    errors: list[str] = []

    declared_events = {str(event) for event in definition.observability.get("persistent_events") or ()}
    implemented_events = {member.value for member in EventType if member.persistence is EventPersistence.PERSISTENT}
    if declared_events != implemented_events:
        errors.append(
            f"observability.persistent_events != EventType vocabulary "
            f"(yaml-only={sorted(declared_events - implemented_events)}, "
            f"code-only={sorted(implemented_events - declared_events)})"
        )

    vocabularies = (
        ("execution_status", ExecutionStatus),
        ("criterion_result", CriterionResult),
        ("capability_coverage", CapabilityCoverage),
    )
    for name, enum_type in vocabularies:
        declared = {str(value) for value in definition.vocabularies.get(name) or ()}
        implemented = {member.value for member in enum_type}
        if declared != implemented:
            errors.append(f"vocabularies.{name} != {enum_type.__name__} values")

    stage_owners = {stage.id: stage.owner for stage in definition.stages}
    for owner, block in (definition.ownership or {}).items():
        for stage_id in (block or {}).get("stages") or []:
            actual = stage_owners.get(str(stage_id))
            if actual is None:
                errors.append(f"ownership.{owner} lists unknown stage {stage_id!r}")
            elif actual != owner:
                errors.append(f"ownership.{owner} lists {stage_id!r} but the stage owner is {actual!r}")

    for stage in definition.stages:
        if stage.authorization_checks and tuple(stage.authorization_checks) != safety.AUTHORIZATION_CHECKS:
            errors.append(f"{stage.id}: authorization_checks diverged from the implemented safety checks")
        sync_block = stage.synchronization or {}
        declared_requires = tuple(str(require) for require in sync_block.get("requires") or ())
        if declared_requires and declared_requires != safety.SYNCHRONIZATION_REQUIRES:
            errors.append(f"{stage.id}: synchronization.requires diverged from the implemented safety requirements")

    if str(definition.digests.get("algorithm") or "") != canonical.DIGEST_ALGORITHM:
        errors.append("digests.algorithm does not match the canonical digest implementation")

    on_exceeded = definition.cost_budget.get("on_exceeded") or {}
    if not on_exceeded.get("terminal_outcome") or not on_exceeded.get("reason"):
        errors.append("cost_budget.on_exceeded must declare terminal_outcome and reason")

    loopback_target = (definition.approval_boundary.get("changes_to_approved_package") or {}).get("return_to")
    if loopback_target is not None and str(loopback_target) != "implementation_planning":
        errors.append("approval_boundary.changes_to_approved_package.return_to must target implementation_planning")

    # processing_plan_activation: the declared plan must be produced by an earlier
    # stage, activated by runtime, and required by the approve destination.
    stage_ids = set(definition.stage_ids())
    for stage in definition.stages:
        activation = stage.processing_plan_activation
        if not activation:
            continue
        plan_key = str(activation.get("plan") or "")
        if str(activation.get("activated_by") or "") != "runtime":
            errors.append(f"{stage.id}: processing_plan_activation.activated_by must be runtime")
        producers = [
            other.id for other in definition.stages if plan_key in other.produces and other.order < stage.order
        ]
        if not producers:
            errors.append(
                f"{stage.id}: processing_plan_activation plan {plan_key!r} is not produced by any earlier stage"
            )
        destination = stage.transitions.get("on_approve")
        if (
            isinstance(destination, str)
            and destination in stage_ids
            and plan_key not in definition.get_stage(destination).requires
        ):
            errors.append(
                f"{stage.id}: activated plan {plan_key!r} is not required by approve destination {destination!r}"
            )

    if errors:
        raise ContractConfigurationError("definition consistency violations: " + "; ".join(errors))
