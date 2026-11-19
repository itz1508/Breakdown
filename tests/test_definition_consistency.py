"""Final cycle — definition-consistency pinning and data-driven policy consumption."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from breakdown.contracts import ContractConfigurationError, validate_definition_consistency
from breakdown.engine import load_workflow
from breakdown.models import (
    ArtifactRef,
    BuildExecutionInput,
    CriterionResult,
    ImplementationPlan,
    PreflightResult,
    ProcessingPlan,
    SourceCheckpoint,
    TokenUsage,
)
from breakdown.roles.builder import Builder

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / "breakdown.yaml"


def _definition():  # type: ignore[no-untyped-def]
    return load_workflow(WORKFLOW)


def _mutate(tmp_path: Path, mutate) -> Any:  # type: ignore[no-untyped-def]
    raw = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "mutated.breakdown.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return load_workflow(path)


def test_real_definition_passes_consistency() -> None:
    validate_definition_consistency(_definition())


def test_event_catalog_drift_fails(tmp_path: Path) -> None:
    def drop_event(raw: dict[str, Any]) -> None:
        raw["observability"]["persistent_events"].remove("cost_threshold_approached")

    definition = _mutate(tmp_path, drop_event)
    with pytest.raises(ContractConfigurationError, match="observability"):
        validate_definition_consistency(definition)


def test_vocabulary_drift_fails(tmp_path: Path) -> None:
    def drop_criterion(raw: dict[str, Any]) -> None:
        raw["vocabularies"]["criterion_result"].remove("uncertainty")

    definition = _mutate(tmp_path, drop_criterion)
    with pytest.raises(ContractConfigurationError, match="criterion_result"):
        validate_definition_consistency(definition)


def test_ownership_drift_fails(tmp_path: Path) -> None:
    def misassign(raw: dict[str, Any]) -> None:
        raw["ownership"]["auditor"]["stages"].append("build_execution")

    definition = _mutate(tmp_path, misassign)
    with pytest.raises(ContractConfigurationError, match="ownership"):
        validate_definition_consistency(definition)


def test_authorization_checks_drift_fails(tmp_path: Path) -> None:
    def drop_check(raw: dict[str, Any]) -> None:
        for stage in raw["stages"]:
            if stage["id"] == "build_execution":
                stage["authorization_checks"].pop()

    definition = _mutate(tmp_path, drop_check)
    with pytest.raises(ContractConfigurationError, match="authorization_checks"):
        validate_definition_consistency(definition)


def test_sync_requires_drift_fails(tmp_path: Path) -> None:
    def drop_require(raw: dict[str, Any]) -> None:
        for stage in raw["stages"]:
            if stage["id"] == "build_execution":
                stage["synchronization"]["requires"].pop()

    definition = _mutate(tmp_path, drop_require)
    with pytest.raises(ContractConfigurationError, match=r"synchronization\.requires"):
        validate_definition_consistency(definition)


def test_digest_algorithm_drift_fails(tmp_path: Path) -> None:
    def wrong_algorithm(raw: dict[str, Any]) -> None:
        raw["digests"]["algorithm"] = "md5"

    definition = _mutate(tmp_path, wrong_algorithm)
    with pytest.raises(ContractConfigurationError, match=r"digests\.algorithm"):
        validate_definition_consistency(definition)


def test_processing_plan_activation_drift_fails(tmp_path: Path) -> None:
    def ghost_plan(raw: dict[str, Any]) -> None:
        for stage in raw["stages"]:
            if stage["id"] == "research_approval":
                stage["processing_plan_activation"]["plan"] = "ghost_plan"

    definition = _mutate(tmp_path, ghost_plan)
    with pytest.raises(ContractConfigurationError, match="processing_plan_activation"):
        validate_definition_consistency(definition)


def _load_t7b():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "t7b_harness_final", Path(__file__).resolve().parent / "test_engine_budget_recovery.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _two_task_plan() -> ImplementationPlan:
    task = {
        "task_id": "task-1",
        "sequence": 1,
        "responsibility": "first change",
        "requirement_refs": ["req-1"],
        "target_paths": [{"path": "src/calc.py", "disposition": "modify"}],
        "source_evidence": ["f-1"],
        "capability_reuse": [],
        "reference_ids": [],
        "expected_result": "change applied",
        "validation_steps": [
            {"step_id": "v-1", "description": "check", "command_or_observation": "look", "expected": "ok"}
        ],
        "required_evidence": ["observation"],
    }
    second = dict(
        task,
        task_id="task-2",
        sequence=2,
        target_paths=[{"path": "tests/test_calc.py", "disposition": "modify"}],
    )
    return ImplementationPlan.model_validate(
        {
            "plan_id": "plan-2t",
            "revision": 1,
            "objective": "two tasks",
            "requirement_refs": ["req-1"],
            "source_checkpoint_ref": {"artifact_key": "source_checkpoint", "digest": "1" * 64},
            "technology_decisions": [],
            "tasks": [task, second],
            "integration_checks": [],
            "success_criteria": [{"criterion": "done", "measurable": True}],
        }
    )


def _build_input(stop: tuple[str, ...]) -> BuildExecutionInput:
    now = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)
    return BuildExecutionInput(
        implementation_plan=_two_task_plan(),
        frozen_plan_hash="3" * 64,
        preflight_result=PreflightResult(
            criterion=CriterionResult.VALID,
            criteria_results=({"name": "content_hash_match", "criterion": "valid", "evidence": "ok"},),
            checked_at=now,
        ),
        plan_approval_ref=ArtifactRef(artifact_key="plan_approval_record", digest="4" * 64),
        approval_hash="5" * 64,
        approved_plan_revision=1,
        approved_source_checkpoint=SourceCheckpoint(
            repository_identity="t", commit_sha=None, file_hashes={}, captured_at=now
        ),
        processing_plan=ProcessingPlan(
            objective="execute",
            input_refs=["implementation_plan"],
            steps=["apply"],
            expected_output_keys=["task_results"],
            completion_criteria=["evidence-backed"],
            evidence_required=["observations"],
        ),
        stop_on_criterion=stop,
    )


def test_stop_on_criterion_flows_from_definition_to_builder(tmp_path: Path) -> None:
    import asyncio

    from breakdown.models import RunRef, StageContext

    t7b = _load_t7b()
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    context = StageContext(
        run=RunRef(run_id="r", session_id="s", definition_version=1, definition_digest="0" * 64),
        stage_id="build_execution",
    )

    def run(stop: tuple[str, ...]) -> Any:
        backend = t7b.ScriptedCodingBackend(("blocked", "complete"))
        builder = Builder(backend=backend, sandbox_root=tmp_path)
        return asyncio.run(builder.execute_build(_build_input(stop), context))

    # yaml-declared stop criteria (not_valid + uncertainty): first task blocks, second skipped
    output = run(("not_valid", "uncertainty"))
    assert [row.execution_result.value for row in output.task_results] == ["blocked", "skipped"]

    # narrowed criteria (only not_valid): uncertainty does not stop the build
    output = run(("not_valid",))
    assert [row.execution_result.value for row in output.task_results] == ["blocked", "completed"]


def test_on_exceeded_policy_is_data_driven(tmp_path: Path) -> None:
    t7b = _load_t7b()
    raw = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    raw["cost_budget"]["on_exceeded"]["reason"] = "budget_spent"
    raw["cost_budget"]["per_stage"]["default_max_tokens"] = 100
    path = tmp_path / "policy.breakdown.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    h = t7b.Harness(
        tmp_path,
        definition_path=path,
        usage=TokenUsage(input_tokens=60, output_tokens=60, tool_calls=1),
    )
    record = h.run_to_terminal()
    assert record.terminal_outcome == "failed"
    assert record.reason == "budget_spent"  # reason comes from the definition, not the engine
