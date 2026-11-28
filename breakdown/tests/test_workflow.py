"""Task 2 — workflow definition tests.

``breakdown.yaml`` is the single declarative workflow authority. These tests
pin its clean-baseline shape: eight canonical stages, decision contracts,
three processing-plan handoffs, vocabularies, artifact closure, and the
absence of retired stage identifiers.

Task 7 extends this module with engine-level rows (forward DAG via graphlib,
bounded loop-back validation, resolve_next).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

DEFINITION_PATH = Path(__file__).resolve().parents[2] / "breakdown.yaml"

CANONICAL_STAGES = (
    "research_proposal",
    "research_approval",
    "research_execution",
    "findings_review",
    "implementation_planning",
    "plan_approval",
    "build_execution",
    "completion",
)

EXPECTED_KIND = {
    "research_proposal": "role",
    "research_approval": "decision",
    "research_execution": "role",
    "findings_review": "role",
    "implementation_planning": "role",
    "plan_approval": "decision",
    "build_execution": "role",
    "completion": "deterministic",
}

EXPECTED_OWNER = {
    "research_proposal": "auditor",
    "research_approval": "user",
    "research_execution": "researcher",
    "findings_review": "auditor",
    "implementation_planning": "planner",
    "plan_approval": "user",
    "build_execution": "builder",
    "completion": "runtime",
}

EXPECTED_OPERATION = {
    "research_proposal": "create_research_proposal",
    "research_approval": "record_research_approval",
    "research_execution": "execute_research",
    "findings_review": "review_research_findings",
    "implementation_planning": "create_implementation_plan",
    "plan_approval": "record_plan_approval",
    "build_execution": "execute_build",
    "completion": "record_completion",
}

PROCESSING_PLAN_HANDOFFS = {
    "research_proposal": ("research_execution_processing_plan", "research_execution", "auditor"),
    "findings_review": ("implementation_planning_processing_plan", "implementation_planning", "auditor"),
    "implementation_planning": ("build_execution_processing_plan", "build_execution", "planner"),
}

# v5-era, v6-era, and scaffold-era identifiers must never reappear.
RETIRED_STAGE_IDS = frozenset(
    {
        "user_input",
        "prepare_request",
        "specification_review",
        "specification_check",
        "repository_audit",
        "check_plan",
        "plan_confirmation",
        "research_confirmation",
        "gate_1",
        "audit_pre_research",
        "audit_post_research",
        "build",
    }
)


@pytest.fixture(scope="module")
def definition() -> dict[str, Any]:
    with DEFINITION_PATH.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="module")
def stages(definition: dict[str, Any]) -> list[dict[str, Any]]:
    loaded = definition["stages"]
    assert isinstance(loaded, list)
    return loaded


def _stage(stages: list[dict[str, Any]], stage_id: str) -> dict[str, Any]:
    for stage in stages:
        if stage["id"] == stage_id:
            return stage
    raise AssertionError(f"stage {stage_id!r} not found")


def _decision_outputs(stage: dict[str, Any]) -> set[str]:
    by_action = stage.get("output_by_action", {})
    outputs: set[str] = set()
    for action_outputs in by_action.values():
        outputs.update(action_outputs)
    outputs.update(stage.get("produces", []))
    return outputs


def test_definition_identity(definition: dict[str, Any]) -> None:
    assert definition["workflow_id"] == "oneshot.breakdown"
    assert definition["definition_version"] == 3


def test_eight_canonical_stages_in_order(stages: list[dict[str, Any]]) -> None:
    ids = [stage["id"] for stage in stages]
    assert tuple(ids) == CANONICAL_STAGES
    orders = [stage["order"] for stage in stages]
    assert orders == list(range(1, len(CANONICAL_STAGES) + 1))


def test_final_review_is_runtime_methodology_not_a_workflow_stage(
    definition: dict[str, Any], stages: list[dict[str, Any]]
) -> None:
    methodology = definition["definition"]["runtime_methodologies"]["final_review"]
    assert methodology["classification"] == "runtime_methodology"
    assert methodology["workflow_stage"] is False
    assert methodology["boundary"] == {
        "runs_after": "implementation_planning",
        "completes_before": "plan_approval",
    }
    assert methodology["tool"]["id"] == "verify_all"
    assert methodology["tool"]["ordered_operations"] == [
        "run_preflight",
        "compute_plan_sha256",
        "compute_source_checkpoint_sha256",
        "generate_confirmation_id",
        "compute_combined_seal_sha256",
        "persist_preconfirmation_seal",
    ]
    assert methodology["tool"]["authority"]["authorizes_builder_mutation"] is False
    assert methodology["preconfirmation"]["seal_status_does_not_mean"] == "user_approved"
    assert methodology["while_awaiting_confirmation"]["host_runs_in_background"] is True
    assert methodology["mutation_release"]["final_integrity_check"] == "immediately_before_builder_mutation"
    assert "final_review" not in {stage["id"] for stage in stages}


def test_workflow_labels_keep_methodology_out_of_stage_list(definition: dict[str, Any]) -> None:
    labels = definition["definition"]["workflow_labels"]
    assert labels["plan_approval"] == "Await User Confirmation"
    assert labels["build_execution"] == "Builder — Mutation"
    assert labels["completion"] == "Final_result"
    assert "final_review" not in labels


def test_stage_kinds_owners_operations(stages: list[dict[str, Any]]) -> None:
    for stage in stages:
        stage_id = stage["id"]
        assert stage["kind"] == EXPECTED_KIND[stage_id], stage_id
        assert stage["owner"] == EXPECTED_OWNER[stage_id], stage_id
        assert stage["operation"] == EXPECTED_OPERATION[stage_id], stage_id


def test_no_retired_stage_ids(stages: list[dict[str, Any]]) -> None:
    ids = {stage["id"] for stage in stages}
    assert ids.isdisjoint(RETIRED_STAGE_IDS)


def test_decision_stages_declare_options_and_transitions(stages: list[dict[str, Any]]) -> None:
    research_approval = _stage(stages, "research_approval")
    assert research_approval["options"] == ["approve", "cancel"]
    assert research_approval["transitions"]["on_approve"] == "research_execution"
    assert research_approval["transitions"]["on_cancel"] == "completion"

    plan_approval = _stage(stages, "plan_approval")
    assert plan_approval["options"] == ["approve", "request_changes", "decline"]
    assert plan_approval["transitions"]["on_approve"] == "build_execution"
    assert plan_approval["transitions"]["on_decline"] == "completion"

    ids = {stage["id"] for stage in stages}
    for stage in stages:
        for target in stage.get("transitions", {}).values():
            destination = target if isinstance(target, str) else target.get("return_to")
            assert destination in ids, (stage["id"], destination)


def test_plan_approval_loop_back_is_bounded(stages: list[dict[str, Any]]) -> None:
    plan_approval = _stage(stages, "plan_approval")
    changes = plan_approval["transitions"]["on_request_changes"]
    assert changes["return_to"] == "implementation_planning"
    assert changes["max_loops"] >= 1
    assert changes["invalidate"], "request_changes must invalidate the frozen package"
    assert changes["on_exhausted"] == "completion"


def test_three_processing_plan_handoffs(stages: list[dict[str, Any]]) -> None:
    for stage_id, (name, destination, author) in PROCESSING_PLAN_HANDOFFS.items():
        creates = _stage(stages, stage_id)["creates_processing_plan"]
        assert creates["name"] == name, stage_id
        assert creates["destination_stage"] == destination, stage_id
        assert creates["authored_by"] == author, stage_id
        assert creates["schema_ref"] == "processing_plan_schema", stage_id
    creators = [stage["id"] for stage in stages if "creates_processing_plan" in stage]
    assert sorted(creators) == sorted(PROCESSING_PLAN_HANDOFFS)


def test_vocabularies(definition: dict[str, Any]) -> None:
    vocab = definition["vocabularies"]
    assert vocab["criterion_result"] == ["valid", "not_valid", "uncertainty"]
    assert vocab["capability_coverage"] == ["covered", "partial", "not_covered", "uncertainty"]
    assert set(vocab["execution_status"]) == {
        "not_run",
        "in_progress",
        "completed",
        "cancelled",
        "failed",
    }


def test_artifact_closure_and_unique_role_produces(stages: list[dict[str, Any]]) -> None:
    available = {"initial_request"}
    role_produces: list[str] = []
    for stage in stages:
        missing = [key for key in stage.get("requires", []) if key not in available]
        assert not missing, f"{stage['id']} requires unproduced {missing}"
        if stage["kind"] == "role":
            role_produces.extend(stage.get("produces", []))
            available.update(stage.get("produces", []))
            for step in stage.get("runtime_steps", []):
                available.update(step.get("outputs", []))
        elif stage["kind"] == "decision":
            available.update(_decision_outputs(stage))
        else:
            available.update(stage.get("produces", []))
    assert len(role_produces) == len(set(role_produces)), "role-stage produces must be disjoint"


def test_build_execution_requires_approved_package(stages: list[dict[str, Any]]) -> None:
    requires = set(_stage(stages, "build_execution")["requires"])
    assert {
        "implementation_plan",
        "frozen_plan",
        "frozen_plan_hash",
        "preflight_result",
        "plan_approval_record",
        "approval_hash",
        "approved_plan_revision",
        "approved_source_checkpoint",
        "build_execution_processing_plan",
    } <= requires


def test_ownership_alignment(definition: dict[str, Any], stages: list[dict[str, Any]]) -> None:
    ownership = definition["ownership"]
    for stage in stages:
        declared = ownership[stage["owner"]]["stages"]
        assert stage["id"] in declared, (stage["id"], stage["owner"])
    assert ownership["builder"]["application_source_changes"] == "sandbox_only"
    assert "synchronization_authorization" in ownership["builder"]["does_not_own"]
    assert ownership["auditor"]["sub_roles"] == ["coder"]
    assert "workflow_state_authority" in ownership["application"]["owns"]
    assert "user_decision_authority" in ownership["application"]["owns"]
    assert "pending_confirmation_records" in ownership["storage"]["owns"]
    assert "artifact_records" in ownership["storage"]["owns"]
    assert "background_integrity_monitoring" in ownership["runtime"]["owns"]
    assert ownership["runtime"]["methodologies"] == ["final_review"]


def test_approval_boundary(definition: dict[str, Any]) -> None:
    boundary = definition["approval_boundary"]
    requires = set(boundary["implementation_requires"])
    assert "recorded_plan_approval" in requires
    assert "matching_approval_hash" in requires
    assert "matching_source_checkpoint" in requires


def test_handoff_rules_preserve_authority_split(definition: dict[str, Any]) -> None:
    rules = " ".join(definition["handoff_rules"])
    assert "Role processors never invoke the next workflow role directly" in rules
    assert "Lifecycle failure and criterion not_valid are distinct" in rules
