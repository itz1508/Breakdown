"""Workflow engine: definition authority + run lifecycle.

Phase 1 shipped definition loading/validation and transition resolution.
Phase 2 (P2-T7) adds the durable run lifecycle on top of the stores:

- ``start_run`` pins the definition triple and captures the source
  checkpoint (definition.mutation_after_run_start: prohibited),
- ``advance`` executes the contract-driven stage loop until the run pauses
  at a decision stage or reaches a terminal state,
- ``record_decision`` bridges the durable approval manager,
- ``cancel`` routes any non-terminal run to completion/cancelled.

Each CLI invocation is stateless: all state lives in the stores, so a run
can pause at ``awaiting_decision`` and resume in a later process.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError
from breakdown.shared.models import (
    ArtifactRef,
    BuildExecutionInput,
    BuildExecutionOutput,
    BuildVerificationOutput,
    CancellationRecord,
    CheckResult,
    ClassifiedFinding,
    ContractKind,
    CostSummary,
    CriterionResult,
    EventType,
    FailureRecord,
    FrozenPlan,
    FindingsReviewInput,
    FixtureSpecification,
    ImplementationPlan,
    ImplementationPlanningInput,
    InitialRequest,
    NormalizedEvidence,
    PlanApprovalRecord,
    PreflightResult,
    ProcessingPlan,
    ResearchExecutionInput,
    ResearchProposalInput,
    ResearchProposalOutput,
    ResearchRecord,
    RoleBackend,
    RunRecord,
    RunRef,
    RunState,
    SourceCheckpoint,
    StageContext,
    StageResult,
    StoredValue,
    SynchronizationResult,
    TokenUsage,
    UnresolvedQuestion,
    WorkflowDefinition,
)
from breakdown.system.memory import MemoryStore
from breakdown.system.runtime.approvals import ApprovalManager
from breakdown.system.runtime.completion import build_completion_record, validate_accepts
from breakdown.system.runtime.contracts import (
    activate_role_contract,
    ContractActivationError,
    ContractRegistry,
    StageContract,
)
from breakdown.system.runtime.planning_ops import freeze_plan, run_preflight
from breakdown.system.runtime.verification import (
    build_verification_input,
    parse_verification,
    verification_failure_reason,
    verification_request,
)
from breakdown.system.safety import SafetyBoundary
from breakdown.system.storage.artifact_store import ArtifactStore
from breakdown.system.storage.canonical import (
    approval_hash as compute_approval_hash,
    definition_digest as compute_definition_digest,
    frozen_plan_hash as compute_frozen_plan_hash,
    source_checkpoint_hash,
)
from breakdown.system.storage.checkpoint import capture_source_checkpoint, checkpoint_is_fresh
from breakdown.system.storage.events import EventStore
from breakdown.system.storage.run_store import RunStore

class WorkflowDefinitionError(ValueError):
    """The declarative workflow definition is invalid."""


def _load_definition(path: Path) -> WorkflowDefinition:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowDefinitionError(f"workflow definition not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise WorkflowDefinitionError(f"workflow definition is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkflowDefinitionError("workflow definition must be a mapping")
    try:
        return WorkflowDefinition.model_validate(raw)
    except ValidationError as exc:
        raise WorkflowDefinitionError(f"workflow definition rejected by schema: {exc}") from exc


def _producers(definition: WorkflowDefinition) -> dict[str, str]:
    producers: dict[str, str] = {"initial_request": "<external>"}
    for stage in definition.stages:
        for key in stage.produces:
            producers.setdefault(key, stage.id)
        for action_outputs in stage.output_by_action.values():
            for key in action_outputs:
                producers.setdefault(key, stage.id)
        for step in stage.runtime_steps:
            outputs = step.get("outputs", [])
            if isinstance(outputs, list):
                for key in outputs:
                    producers.setdefault(str(key), stage.id)
    return producers


def _validate_orders(definition: WorkflowDefinition) -> None:
    orders = [stage.order for stage in definition.stages]
    if sorted(orders) != list(range(1, len(orders) + 1)):
        raise WorkflowDefinitionError("stage orders must be unique and contiguous from 1")
    ids = definition.stage_ids()
    if len(ids) != len(set(ids)):
        raise WorkflowDefinitionError("stage ids must be unique")


def _validate_forward_edges(definition: WorkflowDefinition) -> None:
    """Artifact-dependency DAG over stages; cycles are rejected."""
    producers = _producers(definition)
    graph: dict[str, set[str]] = {stage.id: set() for stage in definition.stages}
    for stage in definition.stages:
        for key in stage.requires:
            producer = producers.get(key)
            if producer is None:
                raise WorkflowDefinitionError(f"{stage.id}: requires unproduced artifact {key!r}")
            if producer != "<external>" and producer != stage.id:
                graph[stage.id].add(producer)
    sorter: TopologicalSorter[str] = TopologicalSorter(graph)
    try:
        sorter.prepare()
    except CycleError as exc:
        raise WorkflowDefinitionError(f"forward dependency graph is cyclic: {exc}") from exc


def _validate_loop_backs(definition: WorkflowDefinition) -> None:
    """Loop-back transitions are validated separately from the forward DAG:
    existing earlier target, finite attempts, declared invalidation, and no
    loop-back originating from a non-decision stage."""
    stage_ids = set(definition.stage_ids())
    orders = {stage.id: stage.order for stage in definition.stages}
    for stage in definition.stages:
        changes = stage.transitions.get("on_request_changes")
        if changes is None:
            continue
        if not isinstance(changes, Mapping):
            raise WorkflowDefinitionError(f"{stage.id}: on_request_changes must be a mapping")
        target = changes.get("return_to")
        if not isinstance(target, str) or target not in stage_ids:
            raise WorkflowDefinitionError(f"{stage.id}: loop-back target {target!r} does not exist")
        if orders[target] >= orders[stage.id]:
            raise WorkflowDefinitionError(f"{stage.id}: loop-back must return to an earlier stage")
        max_loops = changes.get("max_loops")
        if not isinstance(max_loops, int) or max_loops < 1:
            raise WorkflowDefinitionError(f"{stage.id}: loop-back requires a finite max_loops >= 1")
        if not changes.get("invalidate"):
            raise WorkflowDefinitionError(f"{stage.id}: loop-back must declare invalidated artifacts")
        if stage.kind is not ContractKind.DECISION:
            raise WorkflowDefinitionError(f"{stage.id}: only decision stages may loop back")
    declared = definition.dependency_validation.get("loop_back_edges", [])
    if isinstance(declared, list):
        for edge in declared:
            if not isinstance(edge, Mapping):
                raise WorkflowDefinitionError("loop_back_edges entries must be mappings")
            if edge.get("from") not in stage_ids or edge.get("to") not in stage_ids:
                raise WorkflowDefinitionError(f"declared loop-back edge does not resolve: {dict(edge)}")
            max_loops = edge.get("max_loops")
            if not isinstance(max_loops, int) or max_loops < 1:
                raise WorkflowDefinitionError(
                    f"declared loop-back edge {edge.get('from')}->{edge.get('to')} requires a finite max_loops >= 1"
                )


def load_workflow(path: str | Path) -> WorkflowDefinition:
    """Load, type-validate, and structurally validate the workflow definition."""
    definition = _load_definition(Path(path))
    _validate_orders(definition)
    _validate_forward_edges(definition)
    _validate_loop_backs(definition)
    return definition


def resolve_next_stage(definition: WorkflowDefinition, current_id: str, *, action: str | None = None) -> str | None:
    """Resolve the forward transition from the current stage.

    Decision stages require the declared action; role/deterministic stages
    follow their declared ``next`` or positional order. Terminal stages
    resolve to None.
    """
    stage = definition.get_stage(current_id)
    if stage.kind is ContractKind.DECISION:
        if action is None:
            raise WorkflowDefinitionError(f"decision stage {current_id!r} requires an action to resolve")
        target = stage.transitions.get(f"on_{action}")
        if isinstance(target, Mapping):
            target = target.get("return_to")
        if not isinstance(target, str):
            raise WorkflowDefinitionError(f"{current_id}: no transition declared for action {action!r}")
        return target
    if stage.next:
        return stage.next
    following = [candidate for candidate in definition.stages if candidate.order == stage.order + 1]
    return following[0].id if following else None


# --- Phase 2 run lifecycle (P2-T7) ---


class EngineError(RuntimeError):
    pass


RoleFactory = Callable[[Path | None], Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class EngineStores:
    artifacts: ArtifactStore
    events: EventStore
    runs: RunStore
    safety: SafetyBoundary
    memory: MemoryStore | None = None


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorkflowEngine:
    """Contract-driven stage loop on top of durable stores.

    The engine owns progression; roles never call each other. Each public
    method runs to the next pause (awaiting_decision) or terminal state and
    returns the stored run record, so CLI invocations stay stateless.
    """

    def __init__(
        self,
        *,
        definition: WorkflowDefinition,
        contracts: ContractRegistry,
        stores: EngineStores,
        approvals: ApprovalManager,
        role_factory: RoleFactory,
        runtime_kind: Literal["offline_demo", "live_openai"] | None = None,
    ) -> None:
        self.definition = definition
        self.contracts = contracts
        self.stores = stores
        self.approvals = approvals
        self.role_factory = role_factory
        self.runtime_kind = runtime_kind
        self._definition_digest = compute_definition_digest(definition.model_dump(mode="json"))

    def _reload(self, run_id: str) -> RunRecord:
        loaded = self.stores.runs.load(run_id)
        if loaded is None:
            raise EngineError(f"run {run_id} not found")
        return loaded[1]

    def _store(self, key: str, model: BaseModel, contract_id: str) -> ArtifactRef:
        return self.stores.artifacts.store_artifact(
            model, key, contract_id=contract_id, contract_version=str(self.definition.definition_version)
        )

    def start_run(self, request_text: str, *, user_identity: str, session_id: str | None = None) -> RunRecord:
        """Pin the definition triple, capture the source checkpoint, create the run."""
        now = _utcnow()
        run_id = f"run-{secrets.token_hex(6)}"
        checkpoint = capture_source_checkpoint(self.stores.safety.target_root)
        request = InitialRequest(text=request_text, created_at=now)
        request_ref = self._store("initial_request", request, "intake")
        checkpoint_ref = self._store("source_checkpoint", checkpoint, "runtime")
        record = RunRecord(
            run_id=run_id,
            session_id=session_id or f"session-{secrets.token_hex(6)}",
            workflow_id=self.definition.workflow_id,
            definition_version=self.definition.definition_version,
            definition_digest=self._definition_digest,
            runtime_kind=self.runtime_kind,
            state=RunState.RUNNING,
            current_stage="research_proposal",
            initial_request_ref=request_ref,
            source_checkpoint_ref=checkpoint_ref,
            produced_artifacts={"initial_request": request_ref, "source_checkpoint": checkpoint_ref},
            created_at=now,
            updated_at=now,
        )
        self.stores.runs.create_run(record)
        return record

    def advance(self, run_id: str) -> RunRecord:
        """Advance the run until it pauses at a decision or goes terminal."""
        while True:
            loaded = self.stores.runs.load(run_id)
            if loaded is None:
                raise EngineError(f"run {run_id} not found")
            revision, record = loaded
            if (
                self.runtime_kind is not None
                and record.runtime_kind is not None
                and record.runtime_kind != self.runtime_kind
            ):
                raise EngineError(
                    f"runtime_kind mismatch for run {run_id}: "
                    f"stored {record.runtime_kind!r} != active {self.runtime_kind!r}"
                )
            if record.state in (RunState.TERMINAL, RunState.AWAITING_DECISION):
                return record
            stage_id = record.current_stage
            if not stage_id:
                raise EngineError(f"run {run_id} has no current stage")
            contract = self.contracts.get(stage_id)
            if contract.kind is ContractKind.DECISION:
                self.stores.events.emit(
                    EventType.STAGE_ENTERED,
                    run_id=run_id,
                    stage_id=stage_id,
                    attempt=record.stage_attempts.get(stage_id, 0) + 1,
                )
                self.approvals.request_decision(run_id)
                return self._reload(run_id)
            if contract.kind is ContractKind.DETERMINISTIC:
                # Forward arrival at completion (only possible from build_execution)
                # means success; failure/cancel routes set terminal_outcome explicitly.
                return self._complete_run(run_id, record.terminal_outcome or "success", record.reason)
            violation = self._budget_violation(record.tokens_used, record.tool_calls_used)
            if violation is not None:
                # cost_budget.on_exceeded: never start another stage once the budget
                # (or the completion reserve) is exhausted.
                self._route_budget_exhausted(run_id, revision, record, stage_id, violation)
                continue
            self.stores.events.emit(
                EventType.STAGE_ENTERED,
                run_id=run_id,
                stage_id=stage_id,
                attempt=record.stage_attempts.get(stage_id, 0) + 1,
            )
            self._run_role_stage(run_id, revision, record, stage_id, contract)

    def _run_role_stage(
        self, run_id: str, revision: int, record: RunRecord, stage_id: str, contract: StageContract
    ) -> None:
        input_value = self._assemble_input(stage_id, record)
        sandbox: Path | None = None
        approved_checkpoint: SourceCheckpoint | None = None
        if stage_id == "build_execution":
            if not isinstance(input_value, BuildExecutionInput):
                self._handle_stage_failure(
                    run_id,
                    revision,
                    record,
                    stage_id,
                    "Host build admission received an invalid build input contract",
                    error_type="approval_binding",
                    allow_recovery=False,
                    attempt=record.stage_attempts.get(stage_id, 0) + 1,
                )
                return
            admission_error = self._validate_build_admission(record, input_value)
            if admission_error is not None:
                self._handle_stage_failure(
                    run_id,
                    revision,
                    record,
                    stage_id,
                    admission_error,
                    error_type="approval_binding",
                    allow_recovery=False,
                    attempt=record.stage_attempts.get(stage_id, 0) + 1,
                )
                return
            approved_checkpoint = input_value.approved_source_checkpoint
            sandbox = self.stores.safety.create_sandbox(run_id, approved_checkpoint)
        roles = self.role_factory(sandbox)
        attempt = record.stage_attempts.get(stage_id, 0) + 1
        context = StageContext(
            run=RunRef(
                run_id=run_id,
                session_id=record.session_id,
                definition_version=record.definition_version,
                definition_digest=record.definition_digest,
            ),
            stage_id=stage_id,
            attempt=attempt,
        )
        stage = self.definition.get_stage(stage_id)
        tokens_before = record.tokens_used
        try:
            result = self._activate_with_timeout(contract, input_value, context, roles, stage.timeout_seconds)
        except TimeoutError:
            self._handle_stage_failure(
                run_id,
                revision,
                record,
                stage_id,
                f"stage timed out after {stage.timeout_seconds}s",
                error_type="timeout",
                attempt=attempt,
            )
            return
        except ContractActivationError as exc:
            self._handle_stage_failure(run_id, revision, record, stage_id, f"activation failed: {exc}", attempt=attempt)
            return
        except Exception as exc:  # role lifecycle failure (backend/operation errors)
            self._handle_stage_failure(
                run_id, revision, record, stage_id, f"stage execution failed: {exc}", attempt=attempt
            )
            return
        role_obj = roles.get(contract.owner)
        usage = getattr(role_obj, "last_usage", None) if role_obj is not None else None
        tokens_used = record.tokens_used + (usage.input_tokens + usage.output_tokens if usage is not None else 0)
        tool_calls_used = record.tool_calls_used + (usage.tool_calls if usage is not None else 0)
        stage_usage = self._add_stage_usage(record.stage_usage, stage_id, usage)
        self._maybe_emit_cost_threshold(run_id, stage_id, tokens_before, tokens_used)
        if result.criterion is CriterionResult.UNCERTAINTY and stage_id != "build_execution":
            # D27: uncertainty outside build routes to completion/failed without recovery.
            self._handle_stage_failure(
                run_id,
                revision,
                record,
                stage_id,
                result.reason or "uncertainty unresolved",
                error_type="uncertainty",
                allow_recovery=False,
                attempt=attempt,
                usage=(tokens_used, tool_calls_used),
                stage_usage=stage_usage,
            )
            return
        if result.criterion is not CriterionResult.VALID:
            self._handle_stage_failure(
                run_id,
                revision,
                record,
                stage_id,
                result.reason or "stage criterion not valid",
                attempt=attempt,
                usage=(tokens_used, tool_calls_used),
                stage_usage=stage_usage,
            )
            return
        produced = dict(record.produced_artifacts)
        for key, value in result.produces.items():
            model = value if isinstance(value, BaseModel) else StoredValue(value=value)
            ref = self._store(key, model, stage_id)
            produced[key] = ref
            self.stores.events.emit(
                EventType.ARTIFACT_PRODUCED,
                run_id=run_id,
                stage_id=stage_id,
                payload={"artifact_key": key, "revision": ref.revision},
            )
        attempts = dict(record.stage_attempts)
        attempts[stage_id] = attempt
        usage_totals = (tokens_used, tool_calls_used)
        failure_reason: str | None = None
        if stage_id == "build_execution":
            build_output = result.produces.get("build_result")
            criteria = (
                {task_result.criterion for task_result in build_output.task_results}
                if isinstance(build_output, BuildExecutionOutput)
                else set()
            )
            if CriterionResult.UNCERTAINTY in criteria:
                # Loopback edge: newly required path or plan contradiction.
                self._loop_back_for_replanning(run_id, revision, record, produced, attempt, usage_totals, stage_usage)
                return
            if CriterionResult.NOT_VALID in criteria:
                failure_reason = "build task returned not_valid"
        if failure_reason is None:
            budget_detail = self._budget_violation(tokens_used, tool_calls_used) or self._stage_cap_violation(
                stage_id, usage
            )
            if budget_detail is not None:
                self._route_budget_exhausted(
                    run_id,
                    revision,
                    record,
                    stage_id,
                    budget_detail,
                    produced=produced,
                    attempts=attempts,
                    usage=usage_totals,
                    stage_usage=stage_usage,
                )
                return
        if stage_id == "implementation_planning" and failure_reason is None:
            failure_reason = self._freeze_and_preflight(run_id, stage_id, produced)
        verification_usage: TokenUsage | None = None
        if stage_id == "build_execution" and failure_reason is None:
            assert approved_checkpoint is not None
            build_output = result.produces.get("build_result")
            plan_ref = produced.get("implementation_plan")
            if not isinstance(build_output, BuildExecutionOutput) or plan_ref is None:
                failure_reason = "build execution did not produce verifiable plan and result artifacts"
            else:
                plan = self.stores.artifacts.get_model(
                    ImplementationPlan, plan_ref.artifact_key, plan_ref.revision
                )
                verifier_output, verification_usage = self._run_independent_verification(
                    run_id=run_id,
                    plan=plan,
                    build_output=build_output,
                    sandbox=sandbox,
                    verifier=roles.get("verifier"),
                )
                verification_ref = self._store(
                    "independent_verification", verifier_output, "build_execution"
                )
                produced["independent_verification"] = verification_ref
                self.stores.events.emit(
                    EventType.ARTIFACT_PRODUCED,
                    run_id=run_id,
                    stage_id=stage_id,
                    payload={
                        "artifact_key": "independent_verification",
                        "revision": verification_ref.revision,
                    },
                )
                if verification_usage is not None:
                    tokens_used += verification_usage.input_tokens + verification_usage.output_tokens
                    tool_calls_used += verification_usage.tool_calls
                    stage_usage = self._add_stage_usage(stage_usage, stage_id, verification_usage)
                    usage_totals = (tokens_used, tool_calls_used)
                    self._maybe_emit_cost_threshold(
                        run_id, stage_id, tokens_used - verification_usage.input_tokens - verification_usage.output_tokens,
                        tokens_used,
                    )
                stage_cap = int(
                    (self.definition.cost_budget.get("per_stage") or {}).get("default_max_tokens") or 0
                )
                stage_tokens = stage_usage.get(stage_id)
                if stage_cap and stage_tokens is not None and stage_tokens.tokens_used > stage_cap:
                    failure_reason = (
                        f"stage {stage_id} consumed {stage_tokens.tokens_used} tokens; "
                        f"per-stage cap {stage_cap}"
                    )
                else:
                    failure_reason = self._budget_violation(tokens_used, tool_calls_used)
                    if failure_reason is None:
                        failure_reason = self._post_build(run_id, produced, approved_checkpoint)
        if failure_reason is not None:
            self._handle_stage_failure(
                run_id,
                revision,
                record,
                stage_id,
                failure_reason,
                attempt=attempt,
                produced=produced,
                usage=usage_totals,
                stage_usage=stage_usage,
            )
            return
        self.stores.events.emit(
            EventType.STAGE_COMPLETED,
            run_id=run_id,
            stage_id=stage_id,
            payload={
                "tokens": tokens_used - record.tokens_used,
                "tool_calls": tool_calls_used - record.tool_calls_used,
            },
        )
        next_stage = resolve_next_stage(self.definition, stage_id)
        if next_stage is None:
            raise EngineError(f"stage {stage_id} has no forward transition")
        self.stores.runs.update_run(
            record.model_copy(
                update={
                    "state": RunState.RUNNING,
                    "current_stage": next_stage,
                    "produced_artifacts": produced,
                    "stage_attempts": attempts,
                    "stage_usage": stage_usage,
                    "tokens_used": tokens_used,
                    "tool_calls_used": tool_calls_used,
                }
            ),
            expected_revision=revision,
        )

    def _load_model(self, record: RunRecord, key: str, model_type: type[BaseModel]) -> Any:
        ref = record.produced_artifacts.get(key)
        if ref is None:
            raise EngineError(f"required artifact {key!r} has not been produced")
        return self.stores.artifacts.get_model(model_type, ref.artifact_key, ref.revision)

    def _load_value(self, record: RunRecord, key: str) -> Any:
        return self._load_model(record, key, StoredValue).value

    def _assemble_input(self, stage_id: str, record: RunRecord) -> BaseModel:
        """Deterministic input assembly from stored artifacts
        (schema_validation point: stage_input_resolution)."""
        if stage_id == "research_proposal":
            return ResearchProposalInput(initial_request=self._load_model(record, "initial_request", InitialRequest))
        if stage_id == "research_execution":
            return ResearchExecutionInput(
                research_proposal=self._load_model(record, "research_proposal", ResearchProposalOutput),
                processing_plan=self._load_model(record, "research_execution_processing_plan", ProcessingPlan),
                research_approval_ref=record.produced_artifacts["research_approval_record"],
                source_checkpoint=self._load_model(record, "source_checkpoint", SourceCheckpoint),
            )
        if stage_id == "findings_review":
            return FindingsReviewInput(
                research_record=self._load_model(record, "research_response", ResearchRecord),
                research_proposal=self._load_model(record, "research_proposal", ResearchProposalOutput),
                exact_user_intent=str(self._load_value(record, "exact_user_intent")),
                source_checkpoint=self._load_model(record, "source_checkpoint", SourceCheckpoint),
            )
        if stage_id == "implementation_planning":
            classified = tuple(
                ClassifiedFinding.model_validate(item) for item in self._load_value(record, "classified_findings")
            )
            normalized = tuple(
                NormalizedEvidence.model_validate(item) for item in self._load_value(record, "normalized_evidence")
            )
            fixtures = tuple(
                FixtureSpecification.model_validate(item)
                for item in self._load_value(record, "reviewed_fixture_specifications")
            )
            unresolved = tuple(
                UnresolvedQuestion.model_validate(item)
                for item in self._load_value(record, "reviewed_unresolved_questions")
            )
            return ImplementationPlanningInput(
                processing_plan=self._load_model(record, "implementation_planning_processing_plan", ProcessingPlan),
                classified_findings=classified,
                normalized_evidence=normalized,
                reviewed_fixture_specifications=fixtures,
                reviewed_unresolved_questions=unresolved,
                exact_user_intent=str(self._load_value(record, "exact_user_intent")),
                source_checkpoint=self._load_model(record, "source_checkpoint", SourceCheckpoint),
            )
        if stage_id == "build_execution":
            approval_record = self._load_model(record, "plan_approval_record", PlanApprovalRecord)
            if not approval_record.approval_hash:
                raise EngineError("plan approval record carries no approval hash")
            return BuildExecutionInput(
                implementation_plan=self._load_model(record, "implementation_plan", ImplementationPlan),
                frozen_plan_hash=str(self._load_value(record, "frozen_plan_hash")),
                preflight_result=self._load_model(record, "preflight_result", PreflightResult),
                plan_approval_ref=record.produced_artifacts["plan_approval_record"],
                approval_hash=approval_record.approval_hash,
                approved_plan_revision=int(self._load_value(record, "approved_plan_revision")),
                approved_source_checkpoint=self._load_model(record, "approved_source_checkpoint", SourceCheckpoint),
                processing_plan=self._load_model(record, "build_execution_processing_plan", ProcessingPlan),
                stop_on_criterion=self.definition.get_stage("build_execution").stop_on_criterion,
            )
        raise EngineError(f"no input assembler for stage {stage_id}")

    def _freeze_and_preflight(self, run_id: str, stage_id: str, produced: dict[str, ArtifactRef]) -> str | None:
        """implementation_planning.runtime_steps: freeze_plan + preflight_check."""
        plan_ref = produced.get("implementation_plan")
        checkpoint_ref = produced.get("source_checkpoint")
        if plan_ref is None or checkpoint_ref is None:
            return "implementation planning did not produce the required artifacts"
        plan = self.stores.artifacts.get_model(ImplementationPlan, plan_ref.artifact_key, plan_ref.revision)
        checkpoint = self.stores.artifacts.get_model(
            SourceCheckpoint, checkpoint_ref.artifact_key, checkpoint_ref.revision
        )
        frozen = freeze_plan(plan=plan, checkpoint=checkpoint, definition_version=self.definition.definition_version)
        frozen_ref = self._store("frozen_plan", frozen, stage_id)
        hash_ref = self._store("frozen_plan_hash", StoredValue(value=frozen.frozen_plan_hash), stage_id)
        required_keys = (
            "classified_findings",
            "normalized_evidence",
            "reviewed_fixture_specifications",
            "reviewed_unresolved_questions",
            "exact_user_intent",
        )
        preflight = run_preflight(
            plan=plan,
            checkpoint=checkpoint,
            target_root=self.stores.safety.target_root,
            required_artifacts={key: key in produced for key in required_keys},
        )
        preflight_ref = self._store("preflight_result", preflight, stage_id)
        produced.update({"frozen_plan": frozen_ref, "frozen_plan_hash": hash_ref, "preflight_result": preflight_ref})
        for key, ref in (
            ("frozen_plan", frozen_ref),
            ("frozen_plan_hash", hash_ref),
            ("preflight_result", preflight_ref),
        ):
            self.stores.events.emit(
                EventType.ARTIFACT_PRODUCED,
                run_id=run_id,
                stage_id=stage_id,
                payload={"artifact_key": key, "revision": ref.revision},
            )
        if preflight.criterion is not CriterionResult.VALID:
            blocked = sorted(
                row.name for row in preflight.criteria_results if row.criterion is not CriterionResult.VALID
            )
            return f"preflight not valid: {blocked}"
        return None

    def _validate_build_admission(
        self,
        record: RunRecord,
        input_value: BuildExecutionInput,
    ) -> str | None:
        """Verify exact approval/package/source bindings before creating a sandbox."""
        try:
            artifacts = record.produced_artifacts
            required = (
                "plan_approval_record",
                "implementation_plan",
                "frozen_plan",
                "frozen_plan_hash",
                "preflight_result",
                "build_execution_processing_plan",
                "source_checkpoint",
                "approved_source_checkpoint",
                "approved_plan_revision",
            )
            missing = [key for key in required if key not in artifacts]
            if missing:
                return f"Host build admission is missing bound artifacts: {sorted(missing)}"

            approval_ref = artifacts["plan_approval_record"]
            if approval_ref != input_value.plan_approval_ref:
                return "build input approval reference does not match the current run artifact"
            if self.stores.artifacts.get_digest(
                approval_ref.artifact_key, approval_ref.revision
            ) != approval_ref.digest:
                return "plan approval record digest does not match Storage"

            approval = self.stores.artifacts.get_model(
                PlanApprovalRecord, approval_ref.artifact_key, approval_ref.revision
            )
            decision = approval.decision
            if decision.stage_id != "plan_approval" or decision.action != "approve":
                return "Host build admission requires the recorded plan_approval approve decision"
            if decision.run_id != record.run_id or decision.session_id != record.session_id:
                return "plan approval decision is not bound to the current run/session"

            frozen_ref = artifacts["frozen_plan"]
            if approval.frozen_plan_ref != frozen_ref:
                return "plan approval is bound to a different frozen plan reference"
            if self.stores.artifacts.get_digest(
                frozen_ref.artifact_key, frozen_ref.revision
            ) != frozen_ref.digest:
                return "frozen plan digest does not match Storage"
            frozen = self.stores.artifacts.get_model(
                FrozenPlan, frozen_ref.artifact_key, frozen_ref.revision
            )

            plan_ref = artifacts["implementation_plan"]
            if self.stores.artifacts.get_digest(
                plan_ref.artifact_key, plan_ref.revision
            ) != plan_ref.digest:
                return "implementation plan digest does not match Storage"
            plan = self.stores.artifacts.get_model(
                ImplementationPlan, plan_ref.artifact_key, plan_ref.revision
            )
            if frozen.plan != plan or input_value.implementation_plan != plan:
                return "approved implementation plan differs from the frozen plan"
            if (
                approval.implementation_plan_revision != plan.revision
                or input_value.approved_plan_revision != plan.revision
                or self._load_value(record, "approved_plan_revision") != plan.revision
            ):
                return "approved plan revision does not match the frozen implementation plan"

            source_ref = artifacts["source_checkpoint"]
            if approval.source_checkpoint_ref != source_ref:
                return "plan approval is bound to a different source checkpoint reference"
            if self.stores.artifacts.get_digest(
                source_ref.artifact_key, source_ref.revision
            ) != source_ref.digest:
                return "source checkpoint digest does not match Storage"
            source_checkpoint = self.stores.artifacts.get_model(
                SourceCheckpoint, source_ref.artifact_key, source_ref.revision
            )
            approved_checkpoint_ref = artifacts["approved_source_checkpoint"]
            approved_checkpoint = self.stores.artifacts.get_model(
                SourceCheckpoint,
                approved_checkpoint_ref.artifact_key,
                approved_checkpoint_ref.revision,
            )
            expected_checkpoint_hash = source_checkpoint_hash(approved_checkpoint)
            if (
                source_checkpoint_hash(source_checkpoint) != expected_checkpoint_hash
                or source_checkpoint_hash(frozen.source_checkpoint) != expected_checkpoint_hash
                or source_checkpoint_hash(input_value.approved_source_checkpoint) != expected_checkpoint_hash
                or approval.source_checkpoint_hash != expected_checkpoint_hash
            ):
                return "approved source checkpoint does not match the frozen/approval binding"
            if not checkpoint_is_fresh(approved_checkpoint, self.stores.safety.target_root):
                return "approved source checkpoint is stale; Builder was not dispatched"

            frozen_hash = compute_frozen_plan_hash(
                plan, approved_checkpoint, record.definition_version
            )
            frozen_hash_ref = artifacts["frozen_plan_hash"]
            frozen_hash_value = self.stores.artifacts.get_model(
                StoredValue, frozen_hash_ref.artifact_key, frozen_hash_ref.revision
            ).value
            if (
                frozen.frozen_plan_hash != frozen_hash
                or str(frozen_hash_value) != frozen_hash
                or input_value.frozen_plan_hash != frozen_hash
                or approval.frozen_plan_hash != frozen_hash
            ):
                return "frozen plan hash does not match the approved package"

            processing_ref = artifacts["build_execution_processing_plan"]
            if approval.build_execution_processing_plan_ref != processing_ref:
                return "plan approval is bound to a different build processing plan"
            if self.stores.artifacts.get_digest(
                processing_ref.artifact_key, processing_ref.revision
            ) != approval.build_execution_processing_plan_digest:
                return "build processing plan digest does not match the approval binding"
            processing = self.stores.artifacts.get_model(
                ProcessingPlan, processing_ref.artifact_key, processing_ref.revision
            )
            if processing != input_value.processing_plan:
                return "build processing plan differs from the approved processing plan"

            preflight_ref = artifacts["preflight_result"]
            if approval.preflight_result_ref != preflight_ref:
                return "plan approval is bound to a different preflight result"
            if self.stores.artifacts.get_digest(
                preflight_ref.artifact_key, preflight_ref.revision
            ) != approval.preflight_result_digest:
                return "preflight result digest does not match the approval binding"
            preflight = self.stores.artifacts.get_model(
                PreflightResult, preflight_ref.artifact_key, preflight_ref.revision
            )
            if preflight.criterion is not CriterionResult.VALID:
                return "approved preflight result is no longer valid"
            if preflight != input_value.preflight_result:
                return "build input preflight result differs from the approved preflight artifact"

            expected_approval_hash = compute_approval_hash(
                frozen_hash, approved_checkpoint, decision
            )
            if (
                not approval.approval_hash
                or approval.approval_hash != expected_approval_hash
                or input_value.approval_hash != expected_approval_hash
            ):
                return "approval hash does not match the approved plan/source/decision binding"
            return None
        except Exception as exc:
            return (
                "Host build admission could not verify the approved package; "
                f"Builder was not dispatched ({type(exc).__name__})"
            )

    def _approval_bindings_current(self, record: RunRecord) -> bool:
        ref = record.produced_artifacts.get("plan_approval_record")
        if ref is None:
            return False
        return self.stores.artifacts.get_digest(ref.artifact_key, ref.revision) == ref.digest

    def _run_independent_verification(
        self,
        *,
        run_id: str,
        plan: ImplementationPlan,
        build_output: BuildExecutionOutput,
        sandbox: Path | None,
        verifier: Any | None,
    ) -> tuple[BuildVerificationOutput, TokenUsage | None]:
        """Run an independent verifier; absence or exceptions never use Builder self-report."""
        if sandbox is None or not isinstance(verifier, RoleBackend):
            verdicts = tuple(
                CheckResult(
                    check_ref=task.task_id,
                    criterion=CriterionResult.UNCERTAINTY,
                    expected=task.expected_result,
                    actual_observation="independent verifier is not configured or sandbox is unavailable",
                )
                for task in plan.tasks
            )
            return BuildVerificationOutput(task_verifications=verdicts), None

        verification_input = build_verification_input(run_id, plan, build_output, sandbox)
        request = verification_request(verification_input)
        stage = self.definition.get_stage("build_execution")
        try:
            response = self._run_awaitable_with_timeout(
                lambda: verifier.generate(request),
                stage.timeout_seconds,
            )
        except Exception as exc:
            verdicts = tuple(
                CheckResult(
                    check_ref=task.task_ref,
                    criterion=CriterionResult.UNCERTAINTY,
                    expected=task.expected_result,
                    actual_observation=(
                        "independent verifier invocation unavailable: " + type(exc).__name__
                    ),
                )
                for task in verification_input.tasks
            )
            return BuildVerificationOutput(task_verifications=verdicts), None

        verdicts = parse_verification(response, verification_input)
        return BuildVerificationOutput(task_verifications=verdicts), response.usage

    def _post_build(
        self,
        run_id: str,
        produced: dict[str, ArtifactRef],
        approved_checkpoint: SourceCheckpoint,
    ) -> str | None:
        """build_execution.synchronization: detect, authorize, synchronize, reconcile."""
        report = self.stores.safety.detect_changed_paths(run_id, approved_checkpoint)
        build_ref = produced.get("build_result")
        plan_ref = produced.get("implementation_plan")
        if build_ref is None or plan_ref is None:
            return "build execution did not produce the required artifacts"
        build_output = self.stores.artifacts.get_model(BuildExecutionOutput, build_ref.artifact_key, build_ref.revision)
        plan = self.stores.artifacts.get_model(ImplementationPlan, plan_ref.artifact_key, plan_ref.revision)
        approved_paths = {target.path for task in plan.tasks for target in task.target_paths}
        task_results_valid = all(result.criterion is CriterionResult.VALID for result in build_output.task_results)
        verification_ref = produced.get("independent_verification")
        if verification_ref is None:
            return "independent verification artifact is missing"
        verification_output = self.stores.artifacts.get_model(
            BuildVerificationOutput,
            verification_ref.artifact_key,
            verification_ref.revision,
        )
        integration_valid = verification_failure_reason(verification_output.task_verifications) is None
        record = self._reload(run_id)
        sync_result = self.stores.safety.authorize_synchronization(
            report=report,
            approved_paths=approved_paths,
            builder_reported_paths=build_output.observed_changed_paths,
            task_results_valid=task_results_valid,
            integration_valid=integration_valid,
            bindings_current=self._approval_bindings_current(record),
            preconditions_current=checkpoint_is_fresh(approved_checkpoint, self.stores.safety.target_root),
        )
        if not sync_result.authorized:
            produced["synchronization_result"] = self._store("synchronization_result", sync_result, "build_execution")
            return f"synchronization blocked: {sync_result.blocked_reason}"
        copied = self.stores.safety.synchronize(sync_result, run_id=run_id)
        final_result = sync_result.model_copy(update={"copied_paths": copied})
        produced["synchronization_result"] = self._store("synchronization_result", final_result, "build_execution")
        resulting = capture_source_checkpoint(self.stores.safety.target_root)
        produced["resulting_source_checkpoint"] = self._store(
            "resulting_source_checkpoint", resulting, "build_execution"
        )
        self.stores.safety.teardown_sandbox(run_id)
        return None

    @staticmethod
    def _add_stage_usage(
        stage_usage: Mapping[str, CostSummary], stage_id: str, usage: TokenUsage | None
    ) -> dict[str, CostSummary]:
        """Per-stage cost attribution; retries and loopbacks accumulate into the stage."""
        updated = dict(stage_usage)
        if usage is None:
            return updated
        prior = updated.get(stage_id)
        tokens = (prior.tokens_used if prior is not None else 0) + usage.input_tokens + usage.output_tokens
        calls = (prior.tool_calls_used if prior is not None else 0) + usage.tool_calls
        updated[stage_id] = CostSummary(tokens_used=tokens, tool_calls_used=calls)
        return updated

    def _budget_limits(self) -> tuple[int, int, int]:
        """cost_budget numbers, derived from the pinned definition (never redeclared)."""
        budget = self.definition.cost_budget
        workflow = budget.get("per_workflow") or {}
        stage_budget = budget.get("per_stage") or {}
        max_tokens = int(workflow.get("max_tokens") or 0)
        max_calls = int(workflow.get("max_tool_calls") or 0)
        reserve = int(stage_budget.get("completion_reserve") or 0)
        return max_tokens, max_calls, reserve

    def _budget_violation(self, tokens_used: int, tool_calls_used: int) -> str | None:
        max_tokens, max_calls, reserve = self._budget_limits()
        if max_tokens and tokens_used > max_tokens:
            return f"tokens used {tokens_used} exceed workflow max_tokens {max_tokens}"
        if max_calls and tool_calls_used > max_calls:
            return f"tool calls used {tool_calls_used} exceed workflow max_tool_calls {max_calls}"
        if max_tokens and reserve and (max_tokens - tokens_used) < reserve:
            return f"remaining budget {max_tokens - tokens_used} below completion_reserve {reserve}"
        return None

    def _stage_cap_violation(self, stage_id: str, usage: TokenUsage | None) -> str | None:
        stage_cap = int((self.definition.cost_budget.get("per_stage") or {}).get("default_max_tokens") or 0)
        if stage_cap and usage is not None and (usage.input_tokens + usage.output_tokens) > stage_cap:
            used = usage.input_tokens + usage.output_tokens
            return f"stage {stage_id} activation used {used} tokens; per-stage cap {stage_cap}"
        return None

    def _maybe_emit_cost_threshold(self, run_id: str, stage_id: str, before_tokens: int, after_tokens: int) -> None:
        max_tokens, _, _ = self._budget_limits()
        if not max_tokens:
            return
        threshold = (max_tokens * 4) // 5
        if before_tokens < threshold <= after_tokens:
            self.stores.events.emit(
                EventType.COST_THRESHOLD_APPROACHED,
                run_id=run_id,
                stage_id=stage_id,
                payload={"threshold": threshold, "tokens_used": after_tokens, "max_tokens": max_tokens},
            )

    def _route_budget_exhausted(
        self,
        run_id: str,
        revision: int,
        record: RunRecord,
        stage_id: str,
        detail: str,
        *,
        produced: Mapping[str, ArtifactRef] | None = None,
        attempts: Mapping[str, int] | None = None,
        usage: tuple[int, int] | None = None,
        stage_usage: Mapping[str, CostSummary] | None = None,
    ) -> None:
        """cost_budget.on_exceeded: route completion with the terminal outcome and
        reason declared by the definition; artifacts produced so far are preserved."""
        tokens_used, tool_calls_used = usage if usage is not None else (record.tokens_used, record.tool_calls_used)
        merged_usage = dict(stage_usage if stage_usage is not None else record.stage_usage)
        on_exceeded = self.definition.cost_budget.get("on_exceeded") or {}
        terminal_outcome = str(on_exceeded.get("terminal_outcome") or "failed")
        reason = str(on_exceeded.get("reason") or "budget_exhausted")
        merged = dict(record.produced_artifacts)
        if produced:
            merged.update(produced)
        failure = FailureRecord(stage_id=stage_id, error_type=reason, evidence=detail, occurred_at=_utcnow())
        merged["failure_record"] = self._store("failure_record", failure, stage_id)
        merged["budget_exhausted_record"] = self._store(
            "budget_exhausted_record",
            StoredValue(
                value={
                    "detail": detail,
                    "tokens_used": tokens_used,
                    "tool_calls_used": tool_calls_used,
                    "stage_usage": {
                        sid: {"tokens_used": summary.tokens_used, "tool_calls_used": summary.tool_calls_used}
                        for sid, summary in sorted(merged_usage.items())
                    },
                }
            ),
            stage_id,
        )
        merged["retained_evidence"] = self._retained_evidence_ref(record, merged)
        self.stores.events.emit(
            EventType.STAGE_FAILED,
            run_id=run_id,
            stage_id=stage_id,
            payload={"reason": "budget_exhausted", "detail": detail},
        )
        update: dict[str, Any] = {
            "state": RunState.RUNNING,
            "current_stage": "completion",
            "terminal_outcome": terminal_outcome,
            "reason": reason,
            "produced_artifacts": merged,
            "resume_point": stage_id,
            "stage_usage": merged_usage,
            "tokens_used": tokens_used,
            "tool_calls_used": tool_calls_used,
        }
        if attempts is not None:
            update["stage_attempts"] = dict(attempts)
        self.stores.runs.update_run(record.model_copy(update=update), expected_revision=revision)

    def _loop_back_edge(self, from_stage: str, to_stage: str) -> Mapping[str, Any]:
        """The declared loop-back edge between two stages (definition authority)."""
        declared = self.definition.dependency_validation.get("loop_back_edges") or []
        for edge in declared:
            if isinstance(edge, Mapping) and edge.get("from") == from_stage and edge.get("to") == to_stage:
                return edge
        raise EngineError(f"no declared loop-back edge {from_stage} -> {to_stage}")

    def _loop_back_for_replanning(
        self,
        run_id: str,
        revision: int,
        record: RunRecord,
        produced: Mapping[str, ArtifactRef],
        attempt: int,
        usage: tuple[int, int],
        stage_usage: Mapping[str, CostSummary],
    ) -> None:
        """build_execution loopback edge (newly_required_path_or_plan_contradiction):
        uncertainty returns to implementation_planning; synchronization is prohibited,
        the sandbox is torn down, and the revised plan requires a new approval.
        The bound is the edge's declared max_loops (definition authority, D29)."""
        edge = self._loop_back_edge("build_execution", "implementation_planning")
        max_loops = int(edge.get("max_loops") or 0)
        self.stores.safety.teardown_sandbox(run_id)
        tokens_used, tool_calls_used = usage
        attempts = dict(record.stage_attempts)
        attempts["build_execution"] = attempt
        if attempt > max_loops:
            self._handle_stage_failure(
                run_id,
                revision,
                record,
                "build_execution",
                "build uncertainty persisted beyond the loopback limit",
                attempt=attempt,
                error_type="uncertainty",
                allow_recovery=False,
                produced=dict(produced),
                usage=usage,
                stage_usage=stage_usage,
            )
            return
        self.stores.events.emit(
            EventType.STAGE_FAILED,
            run_id=run_id,
            stage_id="build_execution",
            payload={"loopback": "implementation_planning", "attempt": attempt},
        )
        self.stores.runs.update_run(
            record.model_copy(
                update={
                    "state": RunState.RUNNING,
                    "current_stage": "implementation_planning",
                    "produced_artifacts": dict(produced),
                    "stage_attempts": attempts,
                    "resume_point": "implementation_planning",
                    "reason": "build returned uncertainty; replanning and new approval required",
                    "stage_usage": dict(stage_usage),
                    "tokens_used": tokens_used,
                    "tool_calls_used": tool_calls_used,
                }
            ),
            expected_revision=revision,
        )

    def _retained_evidence_ref(self, record: RunRecord, produced: Mapping[str, ArtifactRef]) -> ArtifactRef:
        """Retained evidence for terminal routing: refs produced so far (completion accepts requirement)."""
        merged = dict(record.produced_artifacts)
        merged.update(produced)
        value = [
            {"artifact_key": ref.artifact_key, "revision": ref.revision, "digest": ref.digest}
            for _, ref in sorted(merged.items())
        ]
        return self._store("retained_evidence", StoredValue(value=value), "runtime")

    @staticmethod
    def _run_awaitable_with_timeout(
        operation: Callable[[], Awaitable[Any]],
        timeout_seconds: int | None,
    ) -> Any:
        """Run async work safely from sync Runtime code, even inside an active event loop."""
        async def _bounded() -> Any:
            awaitable = operation()
            if timeout_seconds is None:
                return await awaitable
            return await asyncio.wait_for(awaitable, timeout=float(timeout_seconds))

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _bounded()).result()

        return asyncio.run(_bounded())

    @staticmethod
    def _activate_with_timeout(
        contract: StageContract,
        input_value: BaseModel,
        context: StageContext,
        roles: Mapping[str, Any],
        timeout_seconds: int | None,
    ) -> StageResult:
        """Contract activation bounded by the stage's declared timeout_seconds."""
        return WorkflowEngine._run_awaitable_with_timeout(
            lambda: activate_role_contract(contract, input_value, context, roles),
            timeout_seconds,
        )

    def _handle_stage_failure(
        self,
        run_id: str,
        revision: int,
        record: RunRecord,
        stage_id: str,
        reason: str,
        *,
        attempt: int,
        error_type: str = "stage_failed",
        allow_recovery: bool = True,
        produced: Mapping[str, ArtifactRef] | None = None,
        usage: tuple[int, int] | None = None,
        stage_usage: Mapping[str, CostSummary] | None = None,
    ) -> None:
        """stage.on_failure routing: a recoverable stage retries in place until
        max_recovery_attempts is exhausted; any other failure routes to
        completion/failed with failure_record + retained_evidence (completion accepts)."""
        tokens_used, tool_calls_used = usage if usage is not None else (record.tokens_used, record.tool_calls_used)
        merged_usage = dict(stage_usage if stage_usage is not None else record.stage_usage)
        merged = dict(record.produced_artifacts)
        if produced:
            merged.update(produced)
        attempts = dict(record.stage_attempts)
        attempts[stage_id] = attempt
        on_failure = self.definition.get_stage(stage_id).on_failure or {}
        route = str(on_failure.get("route", "completion"))
        max_recovery = int(on_failure.get("max_recovery_attempts", 0))
        if allow_recovery and route == "runtime_recovery" and attempt <= max_recovery:
            self.stores.events.emit(
                EventType.STAGE_FAILED,
                run_id=run_id,
                stage_id=stage_id,
                payload={"recovery": "retry", "attempt": attempt, "reason": reason},
            )
            self.stores.runs.update_run(
                record.model_copy(
                    update={
                        "state": RunState.RUNNING,
                        "current_stage": stage_id,
                        "produced_artifacts": merged,
                        "stage_attempts": attempts,
                        "resume_point": str(on_failure.get("resume_at", stage_id)),
                        "reason": f"recovery scheduled: {reason}",
                        "stage_usage": merged_usage,
                        "tokens_used": tokens_used,
                        "tool_calls_used": tool_calls_used,
                    }
                ),
                expected_revision=revision,
            )
            return
        failure = FailureRecord(stage_id=stage_id, error_type=error_type, evidence=reason, occurred_at=_utcnow())
        merged["failure_record"] = self._store("failure_record", failure, stage_id)
        merged["retained_evidence"] = self._retained_evidence_ref(record, merged)
        self.stores.events.emit(
            EventType.STAGE_FAILED,
            run_id=run_id,
            stage_id=stage_id,
            payload={"recovery": "none", "reason": reason},
        )
        self.stores.runs.update_run(
            record.model_copy(
                update={
                    "state": RunState.RUNNING,
                    "current_stage": "completion",
                    "terminal_outcome": "failed",
                    "reason": reason,
                    "produced_artifacts": merged,
                    "stage_attempts": attempts,
                    "resume_point": stage_id,
                    "stage_usage": merged_usage,
                    "tokens_used": tokens_used,
                    "tool_calls_used": tool_calls_used,
                }
            ),
            expected_revision=revision,
        )

    def _complete_run(self, run_id: str, outcome: str, reason: str) -> RunRecord:
        """Deterministic completion stage: accepts-matrix validation + terminal record."""
        loaded = self.stores.runs.load(run_id)
        if loaded is None:
            raise EngineError(f"run {run_id} not found")
        revision, record = loaded
        if record.state is RunState.TERMINAL:
            return record
        accepts = self.definition.get_stage("completion").accepts or {}
        missing = validate_accepts(accepts, outcome, record.produced_artifacts.keys())
        if missing:
            raise EngineError(f"completion accepts matrix unmet for {outcome!r}: missing {sorted(missing)}")
        changed_paths: tuple[str, ...] = ()
        sync_ref = record.produced_artifacts.get("synchronization_result")
        if sync_ref is not None:
            sync = self.stores.artifacts.get_model(SynchronizationResult, sync_ref.artifact_key, sync_ref.revision)
            changed_paths = sync.copied_paths
        validation_results: tuple[CheckResult, ...] = ()
        build_ref = record.produced_artifacts.get("build_result")
        if build_ref is not None:
            build_output = self.stores.artifacts.get_model(
                BuildExecutionOutput, build_ref.artifact_key, build_ref.revision
            )
            validation_results = build_output.validation_results
        retained_ref = record.produced_artifacts.get("retained_evidence")
        completion = build_completion_record(
            outcome=outcome,
            changed_paths=changed_paths,
            validation_results=validation_results,
            retained_evidence=(retained_ref,) if retained_ref is not None else (),
            resulting_source_checkpoint=record.produced_artifacts.get("resulting_source_checkpoint"),
            tokens_used=record.tokens_used,
            tool_calls_used=record.tool_calls_used,
            stage_usage=record.stage_usage,
            completed_at=_utcnow(),
        )
        completion_ref = self._store("completion_record", completion, "completion")
        produced = dict(record.produced_artifacts)
        produced["completion_record"] = completion_ref
        self.stores.events.emit(
            EventType.RUN_COMPLETED, run_id=run_id, stage_id="completion", payload={"outcome": outcome}
        )
        self.stores.runs.update_run(
            record.model_copy(
                update={
                    "state": RunState.TERMINAL,
                    "current_stage": "completion",
                    "terminal_outcome": outcome,
                    "reason": reason,
                    "produced_artifacts": produced,
                }
            ),
            expected_revision=revision,
        )
        self._write_run_lesson(run_id, record, outcome, reason, changed_paths)
        return self._reload(run_id)

    def _write_run_lesson(
        self, run_id: str, record: RunRecord, outcome: str, reason: str, changed_paths: tuple[str, ...]
    ) -> None:
        """D36: deterministic cross-run memory. Every terminal run leaves one
        lesson document (failures under lessons/, successes under runs/).
        Best-effort: memory is telemetry and must never block the terminal
        state that was just persisted."""
        memory = self.stores.memory
        if memory is None:
            return
        if outcome == "success":
            path = f"runs/{run_id}.md"
            lines = [
                f"# Run record: {run_id}",
                "",
                "- Terminal outcome: success",
                f"- Synchronized paths: {', '.join(changed_paths) if changed_paths else 'none'}",
            ]
        else:
            path = f"lessons/{run_id}.md"
            failed_stage = record.current_stage or "unknown"
            attempts = record.stage_attempts.get(failed_stage, 0)
            lines = [
                f"# Run lesson: {run_id}",
                "",
                f"- Terminal outcome: {outcome}",
                f"- Reason: {reason or 'none recorded'}",
                f"- Failed stage: {failed_stage} (attempt {attempts})",
            ]
        lines.append(f"- Tokens used: {record.tokens_used}; tool calls: {record.tool_calls_used}")
        by_stage = ", ".join(
            f"{stage}={usage.tokens_used}t/{usage.tool_calls_used}tc"
            for stage, usage in sorted(record.stage_usage.items())
        )
        lines.append(f"- Usage by stage: {by_stage or 'none'}")
        lines.append("")
        with contextlib.suppress(Exception):
            memory.write(path, "\n".join(lines), run_id=run_id)

        # Cross-session baseline memory preservation (D40)
        ref = record.produced_artifacts.get("research_response")
        if ref is not None:
            from breakdown.system.memory import store_baseline_map
            from breakdown.shared.models import ResearchRecord

            with contextlib.suppress(Exception):
                resp = self.stores.artifacts.get_model(ResearchRecord, ref.artifact_key, ref.revision)
                if resp.baseline_map is not None:
                    store_baseline_map(memory, resp.baseline_map, run_id=run_id)

    def record_decision(self, run_id: str, action: str, *, user_identity: str, reason: str = "") -> RunRecord:
        outcome = self.approvals.record_decision(run_id, action, user_identity=user_identity, reason=reason)
        if outcome.terminal:
            return self._complete_run(run_id, outcome.terminal_outcome or "failed", outcome.reason)
        return self._reload(run_id)

    def cancel(self, run_id: str, *, reason: str, cancelled_by: Literal["user", "runtime"] = "user") -> RunRecord:
        loaded = self.stores.runs.load(run_id)
        if loaded is None:
            raise EngineError(f"run {run_id} not found")
        revision, record = loaded
        if record.state is RunState.TERMINAL:
            raise EngineError(f"run {run_id} is already terminal")
        cancellation = CancellationRecord(cancelled_by=cancelled_by, reason=reason, occurred_at=_utcnow())
        produced = dict(record.produced_artifacts)
        produced["cancellation_record"] = self._store("cancellation_record", cancellation, "runtime")
        produced["retained_evidence"] = self._retained_evidence_ref(record, produced)
        self.stores.events.emit(EventType.STAGE_CANCELLED, run_id=run_id, stage_id=record.current_stage)
        self.stores.runs.update_run(
            record.model_copy(
                update={
                    "state": RunState.RUNNING,
                    "current_stage": "completion",
                    "terminal_outcome": "cancelled",
                    "reason": reason,
                    "produced_artifacts": produced,
                }
            ),
            expected_revision=revision,
        )
        return self._complete_run(run_id, "cancelled", reason)
