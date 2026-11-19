"""Deterministic completion operations (completion stage, owner: runtime).

The completion stage is deterministic: no backend is involved. These
operations validate the accepts matrix declared by the workflow definition
and build the authoritative CompletionRecord from durable run facts.
``COMPLETION_OPERATIONS`` adapts them to the deterministic-operation
registry shape shared with planning_ops.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from datetime import datetime
from typing import Any, Literal

from breakdown.contracts import DeterministicOperation
from breakdown.models import ArtifactRef, CheckResult, CompletionRecord, CostSummary, StageContext

CompletionOutcome = Literal["success", "partial", "cancelled", "failed"]


class CompletionError(RuntimeError):
    """Completion inputs violate the definition's accepts matrix or vocabulary."""


_OUTCOMES: Mapping[str, CompletionOutcome] = {
    "success": "success",
    "partial": "partial",
    "cancelled": "cancelled",
    "failed": "failed",
}


def _typed_outcome(outcome: str) -> CompletionOutcome:
    typed = _OUTCOMES.get(outcome)
    if typed is None:
        raise CompletionError(f"unknown completion outcome {outcome!r}")
    return typed


def validate_accepts(accepts: Mapping[str, Any], outcome: str, produced_keys: Set[str]) -> tuple[str, ...]:
    """Missing required artifact keys for ``outcome`` under the accepts matrix.

    Data-driven by the definition's completion.accepts block; returns an
    empty tuple when the matrix is satisfied.
    """
    requires = (accepts.get(outcome) or {}).get("requires") or []
    return tuple(str(key) for key in requires if str(key) not in produced_keys)


def terminal_state_for(outcome: str) -> str:
    """completion.terminal_state: success/partial complete the work; otherwise the outcome name."""
    return {"success": "completed", "partial": "completed"}.get(outcome, outcome)


def build_completion_record(
    *,
    outcome: str,
    changed_paths: Sequence[str] = (),
    validation_results: Sequence[CheckResult] = (),
    criterion_results: Sequence[CheckResult] = (),
    remaining_work: Sequence[str] = (),
    retained_evidence: Sequence[ArtifactRef] = (),
    resulting_source_checkpoint: ArtifactRef | None = None,
    tokens_used: int = 0,
    tool_calls_used: int = 0,
    stage_usage: Mapping[str, CostSummary] | None = None,
    completed_at: datetime,
) -> CompletionRecord:
    """Assemble the authoritative CompletionRecord from durable run facts."""
    return CompletionRecord(
        completion_outcome=_typed_outcome(outcome),
        changed_paths=tuple(changed_paths),
        validation_results=tuple(validation_results),
        criterion_results=tuple(criterion_results),
        remaining_work=tuple(remaining_work),
        retained_evidence=tuple(retained_evidence),
        resulting_source_checkpoint=resulting_source_checkpoint,
        cost_summary=CostSummary(
            tokens_used=tokens_used,
            tool_calls_used=tool_calls_used,
            by_stage={sid: summary for sid, summary in sorted((stage_usage or {}).items())},
        ),
        terminal_state=terminal_state_for(outcome),
        completed_at=completed_at,
    )


def record_completion_operation(payload: Mapping[str, Any], context: StageContext) -> Mapping[str, Any]:
    """completion.record_completion: accepts-matrix gate + CompletionRecord.

    Payload: completion_outcome, accepts (definition block), produced_keys,
    changed_paths, retained_evidence, resulting_source_checkpoint,
    tokens_used, tool_calls_used, completed_at.
    """
    outcome = str(payload.get("completion_outcome") or "")
    accepts = payload.get("accepts") or {}
    produced_keys = frozenset(str(key) for key in payload.get("produced_keys") or ())
    missing = validate_accepts(accepts, outcome, produced_keys)
    if missing:
        raise CompletionError(f"accepts matrix unmet for {outcome!r}: missing {sorted(missing)}")
    completed_at = payload.get("completed_at")
    if not isinstance(completed_at, datetime):
        raise CompletionError("record_completion payload requires an aware completed_at datetime")
    completion = build_completion_record(
        outcome=outcome,
        changed_paths=tuple(str(path) for path in payload.get("changed_paths") or ()),
        retained_evidence=tuple(payload.get("retained_evidence") or ()),
        resulting_source_checkpoint=payload.get("resulting_source_checkpoint"),
        tokens_used=int(payload.get("tokens_used") or 0),
        tool_calls_used=int(payload.get("tool_calls_used") or 0),
        completed_at=completed_at,
    )
    return {"completion_record": completion}


COMPLETION_OPERATIONS: Mapping[str, DeterministicOperation] = {
    "record_completion": record_completion_operation,
}
