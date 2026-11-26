"""P2-T6 — planning runtime ops: freeze_plan + the 14 preflight checks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from breakdown.shared.models import (
    CriterionResult,
    ImplementationPlan,
    RunRef,
    StageContext,
)
from breakdown.system.runtime.planning_ops import (
    check_integration_checks_when_needed,
    check_no_uncertainty_in_build_tasks,
    check_required_artifacts_present,
    check_requirement_trace,
    freeze_plan,
    freeze_plan_operation,
    PLANNING_OPERATIONS,
    PlanningOpsError,
    preflight_check_operation,
    run_preflight,
)
from breakdown.system.storage.canonical import frozen_plan_hash
from breakdown.system.storage.checkpoint import capture_source_checkpoint

EXPECTED_CHECK_NAMES = frozenset(
    {
        "source_checkpoint_freshness",
        "implementation_plan_schema_valid",
        "requirement_trace_complete",
        "no_uncertainty_in_build_tasks",
        "all_target_paths_mapped",
        "all_target_dispositions_declared",
        "no_unapproved_path_overlap",
        "capability_reuse_evidence_present",
        "covered_capability_not_reimplemented",
        "partial_capability_has_remaining_responsibility",
        "task_expected_results_present",
        "task_validation_present",
        "integration_checks_present_when_needed",
        "required_artifacts_present",
    }
)


def _now() -> datetime:
    return datetime(2026, 11, 18, tzinfo=UTC)


def _task_payload(task_id: str = "t1", sequence: int = 1, path: str = "src/x.py", **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task_id": task_id,
        "sequence": sequence,
        "responsibility": "resp",
        "requirement_refs": ["r1"],
        "target_paths": [{"path": path, "disposition": "modify"}],
        "expected_result": "ok",
        "validation_steps": [{"step_id": "v1", "description": "d", "command_or_observation": "c", "expected": "e"}],
        "required_evidence": ["ev"],
    }
    payload.update(overrides)
    return payload


def _plan_payload(tasks: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "plan_id": "p1",
        "revision": 1,
        "objective": "o",
        "requirement_refs": ["r1"],
        "source_checkpoint_ref": {"artifact_key": "source_checkpoint", "digest": "d" * 64},
        "tasks": tasks if tasks is not None else [_task_payload()],
        "success_criteria": [{"criterion": "c"}],
    }
    payload.update(overrides)
    return payload


def _plan(**overrides: Any) -> ImplementationPlan:
    return ImplementationPlan.model_validate(_plan_payload(**overrides))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def test_freeze_plan_hash_matches_recipe(repo: Path) -> None:
    checkpoint = capture_source_checkpoint(repo)
    frozen = freeze_plan(plan=_plan(), checkpoint=checkpoint, definition_version=1, frozen_at=_now())
    assert frozen.frozen_plan_hash == frozen_plan_hash(frozen.plan, checkpoint, 1)
    other = freeze_plan(plan=_plan(), checkpoint=checkpoint, definition_version=2, frozen_at=_now())
    assert other.frozen_plan_hash != frozen.frozen_plan_hash


def test_preflight_all_valid_fourteen_rows(repo: Path) -> None:
    checkpoint = capture_source_checkpoint(repo)
    result = run_preflight(
        plan=_plan(), checkpoint=checkpoint, target_root=repo, required_artifacts={"classified_findings": True}
    )
    assert result.criterion is CriterionResult.VALID
    assert len(result.criteria_results) == 14
    assert {row.name for row in result.criteria_results} == EXPECTED_CHECK_NAMES


def test_preflight_detects_checkpoint_drift(repo: Path) -> None:
    checkpoint = capture_source_checkpoint(repo)
    (repo / "src" / "x.py").write_text("x = 2\n", encoding="utf-8")
    result = run_preflight(plan=_plan(), checkpoint=checkpoint, target_root=repo, required_artifacts={})
    assert result.criterion is CriterionResult.NOT_VALID
    row = next(r for r in result.criteria_results if r.name == "source_checkpoint_freshness")
    assert row.criterion is CriterionResult.NOT_VALID


def test_preflight_unresolved_items_block(repo: Path) -> None:
    checkpoint = capture_source_checkpoint(repo)
    plan = _plan(unresolved_items=["which library?"])
    result = run_preflight(plan=plan, checkpoint=checkpoint, target_root=repo, required_artifacts={})
    row = next(r for r in result.criteria_results if r.name == "no_uncertainty_in_build_tasks")
    assert row.criterion is CriterionResult.NOT_VALID
    assert result.criterion is CriterionResult.NOT_VALID


def test_preflight_uncertain_capability_blocks(repo: Path) -> None:
    checkpoint = capture_source_checkpoint(repo)
    task = _task_payload(capability_reuse=[{"capability": "cache", "coverage": "uncertainty"}])
    result = run_preflight(plan=_plan(tasks=[task]), checkpoint=checkpoint, target_root=repo, required_artifacts={})
    row = next(r for r in result.criteria_results if r.name == "no_uncertainty_in_build_tasks")
    assert row.criterion is CriterionResult.NOT_VALID


def test_preflight_missing_required_artifacts(repo: Path) -> None:
    checkpoint = capture_source_checkpoint(repo)
    result = run_preflight(
        plan=_plan(), checkpoint=checkpoint, target_root=repo, required_artifacts={"classified_findings": False}
    )
    row = next(r for r in result.criteria_results if r.name == "required_artifacts_present")
    assert row.criterion is CriterionResult.NOT_VALID


def test_integration_checks_required_for_multiple_tasks() -> None:
    tasks = [_task_payload("t1", 1, "src/a.py"), _task_payload("t2", 2, "src/b.py")]
    plan = _plan(tasks=tasks)
    assert check_integration_checks_when_needed(plan).criterion is CriterionResult.NOT_VALID
    with_checks = _plan(
        tasks=tasks,
        integration_checks=[{"check_id": "i1", "kind": "command", "check": "pytest", "expected": "pass"}],
    )
    assert check_integration_checks_when_needed(with_checks).criterion is CriterionResult.VALID


def test_requirement_trace_check() -> None:
    assert check_requirement_trace(_plan()).criterion is CriterionResult.VALID
    bad = _plan(tasks=[_task_payload(requirement_refs=["ghost"])])
    assert check_requirement_trace(bad).criterion is CriterionResult.NOT_VALID


def test_uncertainty_check_direct() -> None:
    plan = _plan(tasks=[_task_payload(capability_reuse=[{"capability": "c", "coverage": "uncertainty"}])])
    assert check_no_uncertainty_in_build_tasks(plan).criterion is CriterionResult.NOT_VALID


def test_required_artifacts_check() -> None:
    assert check_required_artifacts_present({"a": True}).criterion is CriterionResult.VALID
    assert check_required_artifacts_present({"a": False}).criterion is CriterionResult.NOT_VALID


def _context() -> StageContext:
    return StageContext(
        run=RunRef(run_id="r", session_id="s", definition_version=1, definition_digest="0" * 64),
        stage_id="implementation_planning",
    )


def test_freeze_operation_adapter(repo: Path) -> None:
    checkpoint = capture_source_checkpoint(repo)
    produced = freeze_plan_operation(
        {"implementation_plan": _plan(), "source_checkpoint": checkpoint, "definition_version": 1},
        _context(),
    )
    assert "frozen_plan" in produced
    assert produced["frozen_plan_hash"]


def test_freeze_operation_missing_payload() -> None:
    with pytest.raises(PlanningOpsError):
        freeze_plan_operation({}, _context())


def test_preflight_operation_adapter(repo: Path) -> None:
    checkpoint = capture_source_checkpoint(repo)
    produced = preflight_check_operation(
        {
            "implementation_plan": _plan(),
            "source_checkpoint": checkpoint,
            "target_root": str(repo),
            "required_artifacts": {"classified_findings": True},
        },
        _context(),
    )
    assert produced["preflight_result"].criterion is CriterionResult.VALID


def test_planning_operations_registry() -> None:
    assert set(PLANNING_OPERATIONS) == {"freeze_plan", "preflight_check"}
