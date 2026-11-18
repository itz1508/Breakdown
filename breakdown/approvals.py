"""Durable decision stages: approval requests, binding digests, decision
records, timeouts, and bounded change loops (P2-T5).

Closes the Phase 1 G7 placeholder: decision activation now persists
ResearchApprovalRecord / PlanApprovalRecord with the full decision_binding
fields, computes approval_hash per the canonical recipe, enforces timeouts
on access (D22), and drives the bounded request_changes loop (max_loops
and invalidation lists are read from the definition, never redeclared).
Chat text never becomes a decision; only an explicit recorded action does.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from breakdown.artifact_store import ArtifactStore
from breakdown.canonical import approval_hash as compute_approval_hash
from breakdown.canonical import source_checkpoint_hash
from breakdown.events import EventStore
from breakdown.models import (
    ArtifactRef,
    CancellationRecord,
    ContractKind,
    EventType,
    FrozenPlan,
    PendingDecision,
    PlanApprovalRecord,
    ResearchApprovalRecord,
    RunRecord,
    RunState,
    SourceCheckpoint,
    StageDefinition,
    StoredValue,
    UserDecision,
    WorkflowDefinition,
)
from breakdown.run_store import RunStore

META_BINDING_KEYS = frozenset({"run_id", "session_id", "user_identity", "timestamp"})
PLAN_LOOP_COUNTER = "plan_approval_request_changes"


class ApprovalError(RuntimeError):
    pass


class DecisionNotPending(ApprovalError):
    pass


class ApprovalBindingStale(ApprovalError):
    pass


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    run_id: str
    action: str
    target_stage: str
    terminal: bool
    terminal_outcome: str | None
    reason: str
    produced: Mapping[str, ArtifactRef] = field(default_factory=dict)
    loop_counter: int | None = None
    invalidated_keys: tuple[str, ...] = ()


class ApprovalManager:
    def __init__(
        self,
        *,
        artifacts: ArtifactStore,
        events: EventStore,
        runs: RunStore,
        definition: WorkflowDefinition,
    ) -> None:
        self.artifacts = artifacts
        self.events = events
        self.runs = runs
        self.definition = definition

    def _contract_version(self) -> str:
        return str(self.definition.definition_version)

    def _pending_key(self, stage_id: str) -> str:
        return f"pending_{stage_id}_decision"

    def _load_run(self, run_id: str) -> tuple[int, RunRecord]:
        loaded = self.runs.load(run_id)
        if loaded is None:
            raise ApprovalError(f"run {run_id} not found")
        return loaded

    def _load_pending(self, stage_id: str) -> PendingDecision:
        revision = self.artifacts.latest_revision(self._pending_key(stage_id))
        if revision == 0:
            raise DecisionNotPending(f"no pending decision for stage {stage_id}")
        return self.artifacts.get_model(PendingDecision, self._pending_key(stage_id), revision)

    def _load_checkpoint(self, record: RunRecord) -> SourceCheckpoint:
        ref = record.produced_artifacts.get("source_checkpoint")
        if ref is None:
            raise ApprovalError("source_checkpoint has not been produced")
        return self.artifacts.get_model(SourceCheckpoint, ref.artifact_key, ref.revision)

    def request_decision(self, run_id: str) -> PendingDecision:
        revision, record = self._load_run(run_id)
        if record.state is not RunState.RUNNING:
            raise ApprovalError(f"run {run_id} is not running (state {record.state.value})")
        stage_id = record.current_stage
        if not stage_id:
            raise ApprovalError(f"run {run_id} has no current stage")
        stage = self.definition.get_stage(stage_id)
        if stage.kind is not ContractKind.DECISION:
            raise ApprovalError(f"stage {stage_id} is not a decision stage")
        refs: dict[str, ArtifactRef] = {}
        digests: dict[str, str] = {}
        for bind in (stage.decision_binding or {}).get("binds", []):
            if bind in META_BINDING_KEYS or not bind.endswith("_ref"):
                continue  # meta keys ride on the record; digests/hash pair with their _ref
            artifact_key = bind[: -len("_ref")]
            ref = record.produced_artifacts.get(artifact_key)
            if ref is None:
                raise ApprovalError(f"decision binding {artifact_key!r} has not been produced")
            current = self.artifacts.get_digest(ref.artifact_key, ref.revision)
            if current is None or current != ref.digest:
                raise ApprovalBindingStale(f"binding {artifact_key!r} digest mismatch at request time")
            refs[artifact_key] = ref
            digests[artifact_key] = ref.digest
        pending = PendingDecision(
            run_id=run_id,
            stage_id=stage_id,
            options=tuple(stage.options),
            requested_at=datetime.now(UTC),
            timeout_seconds=stage.timeout_seconds or 86400,
            binding_refs=refs,
            binding_digests=digests,
        )
        self.artifacts.store_artifact(
            pending, self._pending_key(stage_id), contract_id=stage_id, contract_version=self._contract_version()
        )
        self.events.emit(
            EventType.APPROVAL_REQUESTED, run_id=run_id, stage_id=stage_id, payload={"options": list(stage.options)}
        )
        self.runs.update_run(
            record.model_copy(update={"state": RunState.AWAITING_DECISION}), expected_revision=revision
        )
        return pending

    def check_timeout(self, pending: PendingDecision, now: datetime) -> bool:
        return now > pending.requested_at + timedelta(seconds=pending.timeout_seconds)

    def record_decision(
        self,
        run_id: str,
        action: str,
        *,
        user_identity: str,
        reason: str = "",
        decided_at: datetime | None = None,
    ) -> DecisionOutcome:
        revision, record = self._load_run(run_id)
        if record.state is not RunState.AWAITING_DECISION:
            raise DecisionNotPending(f"run {run_id} is not awaiting a decision")
        stage_id = record.current_stage or ""
        stage = self.definition.get_stage(stage_id)
        pending = self._load_pending(stage_id)
        if pending.run_id != run_id:
            raise ApprovalError(f"pending decision belongs to run {pending.run_id}")
        if action not in pending.options:
            raise ApprovalError(f"action {action!r} is not one of {sorted(pending.options)}")
        now = decided_at or datetime.now(UTC)
        if self.check_timeout(pending, now):
            outcome = self._route_timeout(record, stage_id, now)
        else:
            self._verify_bindings_current(record, pending)
            decision = UserDecision(
                stage_id=stage_id,
                action=action,
                reason=reason,
                run_id=run_id,
                session_id=record.session_id,
                user_identity=user_identity,
                decided_at=now,
            )
            if stage_id == "research_approval":
                outcome = self._research_approval(record, decision, pending, now)
            elif stage_id == "plan_approval":
                outcome = self._plan_approval(record, stage, decision, pending, now)
            else:
                raise ApprovalError(f"no approval handling for stage {stage_id}")
        produced_artifacts = dict(record.produced_artifacts)
        produced_artifacts.update(outcome.produced)
        loop_counters = dict(record.loop_counters)
        if outcome.loop_counter is not None:
            loop_counters[PLAN_LOOP_COUNTER] = outcome.loop_counter
        updated = record.model_copy(
            update={
                "state": RunState.RUNNING,
                "current_stage": outcome.target_stage,
                "loop_counters": loop_counters,
                "produced_artifacts": produced_artifacts,
            }
        )
        self.runs.update_run(updated, expected_revision=revision)
        payload: dict[str, object] = {"action": outcome.action}
        if outcome.invalidated_keys:
            payload["invalidated"] = list(outcome.invalidated_keys)
        self.events.emit(EventType.APPROVAL_RECORDED, run_id=run_id, stage_id=stage_id, payload=payload)
        return outcome

    def _verify_bindings_current(self, record: RunRecord, pending: PendingDecision) -> None:
        for artifact_key, ref in pending.binding_refs.items():
            current_ref = record.produced_artifacts.get(artifact_key)
            if current_ref is None or current_ref.revision != ref.revision or current_ref.digest != ref.digest:
                raise ApprovalBindingStale(f"binding {artifact_key!r} changed since the decision was requested")
            stored = self.artifacts.get_digest(ref.artifact_key, ref.revision)
            if stored != ref.digest:
                raise ApprovalBindingStale(f"binding {artifact_key!r} digest mismatch in store")

    def _retained_evidence(self, record: RunRecord) -> ArtifactRef:
        """Retained evidence at terminal routing: refs of everything produced so far."""
        value = [
            {"artifact_key": ref.artifact_key, "revision": ref.revision, "digest": ref.digest}
            for _, ref in sorted(record.produced_artifacts.items())
        ]
        return self.artifacts.store_artifact(
            StoredValue(value=value),
            "retained_evidence",
            contract_id=record.current_stage or "runtime",
            contract_version=self._contract_version(),
        )

    def _route_timeout(self, record: RunRecord, stage_id: str, now: datetime) -> DecisionOutcome:
        cancellation = CancellationRecord(
            cancelled_by="runtime", reason=f"decision timeout at {stage_id}", occurred_at=now
        )
        ref = self.artifacts.store_artifact(
            cancellation, "cancellation_record", contract_id=stage_id, contract_version=self._contract_version()
        )
        return DecisionOutcome(
            run_id=record.run_id,
            action="timeout",
            target_stage="completion",
            terminal=True,
            terminal_outcome="cancelled",
            reason="timeout",
            produced={
                "cancellation_record": ref,
                "retained_evidence": self._retained_evidence(record),
            },
        )

    def _research_approval(
        self, record: RunRecord, decision: UserDecision, pending: PendingDecision, now: datetime
    ) -> DecisionOutcome:
        checkpoint = self._load_checkpoint(record)
        approval_record = ResearchApprovalRecord(
            decision=decision,
            research_proposal_ref=pending.binding_refs["research_proposal"],
            research_proposal_digest=pending.binding_digests["research_proposal"],
            research_execution_processing_plan_ref=pending.binding_refs["research_execution_processing_plan"],
            research_execution_processing_plan_digest=pending.binding_digests["research_execution_processing_plan"],
            source_checkpoint_ref=pending.binding_refs["source_checkpoint"],
            source_checkpoint_hash=source_checkpoint_hash(checkpoint),
        )
        version = self._contract_version()
        ref = self.artifacts.store_artifact(
            approval_record, "research_approval_record", contract_id="research_approval", contract_version=version
        )
        produced = {"research_approval_record": ref}
        if decision.action == "approve":
            return DecisionOutcome(
                run_id=record.run_id,
                action="approve",
                target_stage="research_execution",
                terminal=False,
                terminal_outcome=None,
                reason="",
                produced=produced,
            )
        cancellation = CancellationRecord(
            cancelled_by="user", reason=decision.reason or "research cancelled by user", occurred_at=now
        )
        produced["cancellation_record"] = self.artifacts.store_artifact(
            cancellation, "cancellation_record", contract_id="research_approval", contract_version=version
        )
        produced["retained_evidence"] = self._retained_evidence(record)
        return DecisionOutcome(
            run_id=record.run_id,
            action="cancel",
            target_stage="completion",
            terminal=True,
            terminal_outcome="cancelled",
            reason="user cancelled at research_approval",
            produced=produced,
        )

    def _plan_approval(
        self,
        record: RunRecord,
        stage: StageDefinition,
        decision: UserDecision,
        pending: PendingDecision,
        now: datetime,
    ) -> DecisionOutcome:
        checkpoint = self._load_checkpoint(record)
        frozen_ref = pending.binding_refs["frozen_plan"]
        frozen = self.artifacts.get_model(FrozenPlan, frozen_ref.artifact_key, frozen_ref.revision)
        plan_ref = record.produced_artifacts.get("implementation_plan")
        if plan_ref is None:
            raise ApprovalError("implementation_plan has not been produced")
        approval_record = PlanApprovalRecord(
            decision=decision,
            frozen_plan_ref=frozen_ref,
            frozen_plan_hash=frozen.frozen_plan_hash,
            implementation_plan_revision=plan_ref.revision,
            build_execution_processing_plan_ref=pending.binding_refs["build_execution_processing_plan"],
            build_execution_processing_plan_digest=pending.binding_digests["build_execution_processing_plan"],
            source_checkpoint_ref=pending.binding_refs["source_checkpoint"],
            source_checkpoint_hash=source_checkpoint_hash(checkpoint),
            preflight_result_ref=pending.binding_refs["preflight_result"],
            preflight_result_digest=pending.binding_digests["preflight_result"],
        )
        version = self._contract_version()
        produced: dict[str, ArtifactRef] = {}
        if decision.action == "approve":
            hash_value = compute_approval_hash(frozen.frozen_plan_hash, frozen.source_checkpoint, decision)
            approval_record = approval_record.model_copy(update={"approval_hash": hash_value})
            produced["plan_approval_record"] = self.artifacts.store_artifact(
                approval_record, "plan_approval_record", contract_id="plan_approval", contract_version=version
            )
            produced["approved_plan_revision"] = self.artifacts.store_artifact(
                StoredValue(value=plan_ref.revision),
                "approved_plan_revision",
                contract_id="plan_approval",
                contract_version=version,
            )
            produced["approved_source_checkpoint"] = self.artifacts.store_artifact(
                checkpoint, "approved_source_checkpoint", contract_id="plan_approval", contract_version=version
            )
            return DecisionOutcome(
                run_id=record.run_id,
                action="approve",
                target_stage="build_execution",
                terminal=False,
                terminal_outcome=None,
                reason="",
                produced=produced,
            )
        produced["plan_approval_record"] = self.artifacts.store_artifact(
            approval_record, "plan_approval_record", contract_id="plan_approval", contract_version=version
        )
        if decision.action == "decline":
            cancellation = CancellationRecord(
                cancelled_by="user", reason=decision.reason or "plan declined", occurred_at=now
            )
            produced["cancellation_record"] = self.artifacts.store_artifact(
                cancellation, "cancellation_record", contract_id="plan_approval", contract_version=version
            )
            produced["retained_evidence"] = self._retained_evidence(record)
            return DecisionOutcome(
                run_id=record.run_id,
                action="decline",
                target_stage="completion",
                terminal=True,
                terminal_outcome="cancelled",
                reason="user declined the plan",
                produced=produced,
            )
        # request_changes: bounded loop, derived from the definition
        changes = stage.transitions.get("on_request_changes") or {}
        max_loops = int(changes.get("max_loops", 0))
        invalidated = tuple(str(key) for key in changes.get("invalidate", []))
        counter = record.loop_counters.get(PLAN_LOOP_COUNTER, 0) + 1
        exhausted = counter > max_loops
        return DecisionOutcome(
            run_id=record.run_id,
            action="request_changes",
            target_stage="completion" if exhausted else "implementation_planning",
            terminal=exhausted,
            terminal_outcome="failed" if exhausted else None,
            reason="loop_exhausted" if exhausted else "plan changes requested",
            produced=produced,
            loop_counter=counter,
            invalidated_keys=() if exhausted else invalidated,
        )
