"""P2-T8 — deterministic completion operations + Markdown run reports."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from breakdown.shared.models import ArtifactRef, CompletionRecord, EventType, RunRecord, RunRef, RunState, StageContext
from breakdown.system.runtime.completion import (
    build_completion_record,
    COMPLETION_OPERATIONS,
    CompletionError,
    record_completion_operation,
    terminal_state_for,
    validate_accepts,
)
from breakdown.system.runtime.engine import load_workflow
from breakdown.system.runtime.reports import cite, render_run_report
from breakdown.system.storage.events import EventStore

REPO_ROOT = Path(__file__).resolve().parents[3]


def _definition():  # type: ignore[no-untyped-def]
    return load_workflow(REPO_ROOT / "breakdown.yaml")


def _accepts() -> Mapping[str, Any]:
    return _definition().get_stage("completion").accepts or {}


def _ref(key: str, revision: int = 1) -> ArtifactRef:
    return ArtifactRef(artifact_key=key, revision=revision, digest="ab" * 32)


def _record(produced: Mapping[str, ArtifactRef], **overrides: Any) -> RunRecord:
    now = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)
    base: dict[str, Any] = {
        "run_id": "run-test",
        "workflow_id": "oneshot.breakdown",
        "session_id": "session-test",
        "definition_version": 1,
        "definition_digest": "cd" * 32,
        "state": RunState.TERMINAL,
        "current_stage": "completion",
        "terminal_outcome": "success",
        "initial_request_ref": _ref("initial_request"),
        "source_checkpoint_ref": _ref("source_checkpoint"),
        "produced_artifacts": dict(produced),
        "stage_attempts": {"research_proposal": 1},
        "tokens_used": 1234,
        "tool_calls_used": 7,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return RunRecord(**base)


def test_validate_accepts_satisfied_and_missing() -> None:
    accepts = _accepts()
    success_keys = {
        "approved_plan_revision",
        "build_result",
        "synchronization_result",
        "resulting_source_checkpoint",
        "execution_evidence",
    }
    assert validate_accepts(accepts, "success", success_keys) == ()
    missing = validate_accepts(accepts, "success", success_keys - {"build_result"})
    assert missing == ("build_result",)
    failed_missing = validate_accepts(accepts, "failed", {"failure_record"})
    assert failed_missing == ("retained_evidence",)


@pytest.mark.parametrize("outcome", ["success", "partial", "cancelled", "failed"])
def test_validate_accepts_is_data_driven_for_every_outcome(outcome: str) -> None:
    requires = tuple(_accepts()[outcome]["requires"])
    assert requires, f"yaml accepts.{outcome}.requires must be nonempty"
    assert validate_accepts(_accepts(), outcome, frozenset()) == requires


def test_terminal_state_mapping() -> None:
    assert terminal_state_for("success") == "completed"
    assert terminal_state_for("partial") == "completed"
    assert terminal_state_for("failed") == "failed"
    assert terminal_state_for("cancelled") == "cancelled"


def test_build_completion_record_fields_and_vocabulary() -> None:
    completed_at = datetime(2026, 11, 18, 13, 0, 0, tzinfo=UTC)
    record = build_completion_record(
        outcome="failed",
        changed_paths=("src/calc.py",),
        retained_evidence=(_ref("retained_evidence"),),
        tokens_used=99,
        tool_calls_used=3,
        completed_at=completed_at,
    )
    assert record.completion_outcome == "failed"
    assert record.terminal_state == "failed"
    assert record.changed_paths == ("src/calc.py",)
    assert record.retained_evidence == (_ref("retained_evidence"),)
    assert record.cost_summary is not None
    assert record.cost_summary.tokens_used == 99
    assert record.completed_at == completed_at
    with pytest.raises(CompletionError):
        build_completion_record(outcome="exploded", completed_at=completed_at)


def _context() -> StageContext:
    return StageContext(
        run=RunRef(run_id="run-test", session_id="s", definition_version=1, definition_digest="d" * 64),
        stage_id="completion",
        attempt=1,
    )


def test_record_completion_operation_gate() -> None:
    completed_at = datetime(2026, 11, 18, 13, 0, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "completion_outcome": "cancelled",
        "accepts": _accepts(),
        "produced_keys": ["cancellation_record", "retained_evidence"],
        "retained_evidence": [_ref("retained_evidence")],
        "tokens_used": 10,
        "tool_calls_used": 1,
        "completed_at": completed_at,
    }
    produces = record_completion_operation(payload, _context())
    completion = produces["completion_record"]
    assert isinstance(completion, CompletionRecord)
    assert completion.completion_outcome == "cancelled"

    blocked = dict(payload, produced_keys=["cancellation_record"])
    with pytest.raises(CompletionError, match="retained_evidence"):
        record_completion_operation(blocked, _context())
    no_time = dict(payload)
    no_time.pop("completed_at")
    with pytest.raises(CompletionError, match="completed_at"):
        record_completion_operation(no_time, _context())


def test_completion_operations_registry() -> None:
    assert set(COMPLETION_OPERATIONS) == {"record_completion"}
    assert COMPLETION_OPERATIONS["record_completion"] is record_completion_operation


def test_report_cites_digests_and_is_deterministic() -> None:
    produced = {
        "build_result": _ref("build_result", 2),
        "completion_record": _ref("completion_record"),
        "initial_request": _ref("initial_request"),
    }
    record = _record(produced)
    text = render_run_report(record)
    assert text == render_run_report(record)  # deterministic projection
    for ref in produced.values():
        assert cite(ref) in text
    assert "# Run report: run-test" in text
    assert "terminal outcome: success" in text
    assert "1234 tokens" in text


def test_report_event_summary(tmp_path: Path) -> None:
    events = EventStore(tmp_path / "state")
    events.emit(EventType.STAGE_ENTERED, run_id="run-test", stage_id="research_proposal")
    events.emit(EventType.STAGE_COMPLETED, run_id="run-test", stage_id="research_proposal")
    events.emit(EventType.STAGE_ENTERED, run_id="run-test", stage_id="research_approval")
    text = render_run_report(_record({}), events=events.load("run-test"))
    assert "## Event summary" in text
    assert "- stage_entered: 2" in text
    assert "- stage_completed: 1" in text


def _load_t7b():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "t7b_harness", Path(__file__).resolve().parent / "test_engine_budget_recovery.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_engine_success_completion_wires_operation(tmp_path: Path) -> None:
    t7b = _load_t7b()
    h = t7b.Harness(tmp_path)
    record = h.run_to_terminal()
    assert record.terminal_outcome == "success"
    ref = record.produced_artifacts["completion_record"]
    completion = h.artifacts.get_model(CompletionRecord, ref.artifact_key, ref.revision)
    assert completion.completion_outcome == "success"
    assert completion.terminal_state == "completed"
    assert completion.changed_paths == ("src/calc.py",)
    assert completion.retained_evidence == ()  # success route retains no evidence bundle
    assert completion.cost_summary is not None
    assert completion.cost_summary.tokens_used == record.tokens_used > 0
    # The report projects the terminal record with verifiable citations.
    text = render_run_report(record, events=h.events.load(record.run_id))
    assert cite(ref) in text


def test_engine_failed_completion_retains_evidence(tmp_path: Path) -> None:
    t7b = _load_t7b()
    h = t7b.Harness(tmp_path, role_always_fail={"create_research_proposal": True})
    record = h.run_to_terminal()
    assert record.terminal_outcome == "failed"
    ref = record.produced_artifacts["completion_record"]
    completion = h.artifacts.get_model(CompletionRecord, ref.artifact_key, ref.revision)
    assert completion.terminal_state == "failed"
    assert len(completion.retained_evidence) == 1
    assert completion.retained_evidence[0].artifact_key == "retained_evidence"
