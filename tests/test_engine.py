"""Task F3 — engine tests: definition loading, forward DAG, bounded
loop-backs, transition resolution, and the --check CLI contract."""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from breakdown.engine import WorkflowDefinitionError, load_workflow, resolve_next_stage

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFINITION_PATH = REPO_ROOT / "breakdown.yaml"


@pytest.fixture(scope="module")
def definition():  # type: ignore[no-untyped-def]
    return load_workflow(DEFINITION_PATH)


@pytest.fixture
def base_data() -> dict[str, Any]:
    loaded = yaml.safe_load(DEFINITION_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    file = tmp_path / "workflow.yaml"
    file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return file


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(tmp_path / "nope.yaml")


def test_load_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(":\t- not yaml [", encoding="utf-8")
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(bad)


def test_load_non_mapping(tmp_path: Path) -> None:
    seq = tmp_path / "seq.yaml"
    seq.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(seq)


def test_unknown_top_level_key_rejected(tmp_path: Path, base_data: dict[str, Any]) -> None:
    data = copy.deepcopy(base_data)
    data["rogue_key"] = True
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(_write(tmp_path, data))


def test_cyclic_forward_edges_rejected(tmp_path: Path) -> None:
    data = {
        "workflow_id": "x",
        "definition_version": 1,
        "stages": [
            {
                "id": "a",
                "order": 1,
                "kind": "role",
                "owner": "auditor",
                "operation": "op_a",
                "purpose": "p",
                "requires": ["thing_b"],
                "produces": ["thing_a"],
            },
            {
                "id": "b",
                "order": 2,
                "kind": "role",
                "owner": "auditor",
                "operation": "op_b",
                "purpose": "p",
                "requires": ["thing_a"],
                "produces": ["thing_b"],
            },
        ],
    }
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(_write(tmp_path, data))


def test_unproduced_requires_rejected(tmp_path: Path) -> None:
    data = {
        "workflow_id": "x",
        "definition_version": 1,
        "stages": [
            {
                "id": "a",
                "order": 1,
                "kind": "role",
                "owner": "auditor",
                "operation": "op_a",
                "purpose": "p",
                "requires": ["ghost"],
                "produces": ["thing_a"],
            }
        ],
    }
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(_write(tmp_path, data))


def test_non_contiguous_orders_rejected(tmp_path: Path, base_data: dict[str, Any]) -> None:
    data = copy.deepcopy(base_data)
    data["stages"][2]["order"] = 99
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(_write(tmp_path, data))


def _plan_approval(base_data: dict[str, Any]) -> dict[str, Any]:
    for stage in base_data["stages"]:
        if stage["id"] == "plan_approval":
            return stage
    raise AssertionError("plan_approval stage missing")


def test_loopback_without_max_loops_rejected(tmp_path: Path, base_data: dict[str, Any]) -> None:
    data = copy.deepcopy(base_data)
    del _plan_approval(data)["transitions"]["on_request_changes"]["max_loops"]
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(_write(tmp_path, data))


def test_loopback_to_later_stage_rejected(tmp_path: Path, base_data: dict[str, Any]) -> None:
    data = copy.deepcopy(base_data)
    _plan_approval(data)["transitions"]["on_request_changes"]["return_to"] = "completion"
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(_write(tmp_path, data))


def test_loopback_without_invalidation_rejected(tmp_path: Path, base_data: dict[str, Any]) -> None:
    data = copy.deepcopy(base_data)
    _plan_approval(data)["transitions"]["on_request_changes"]["invalidate"] = []
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(_write(tmp_path, data))


def test_loopback_from_role_stage_rejected(tmp_path: Path, base_data: dict[str, Any]) -> None:
    data = copy.deepcopy(base_data)
    for stage in data["stages"]:
        if stage["id"] == "research_execution":
            stage["transitions"] = {
                "on_request_changes": {
                    "return_to": "research_proposal",
                    "max_loops": 1,
                    "invalidate": ["research_proposal"],
                }
            }
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(_write(tmp_path, data))


def test_declared_loopback_edge_must_resolve(tmp_path: Path, base_data: dict[str, Any]) -> None:
    data = copy.deepcopy(base_data)
    data["dependency_validation"]["loop_back_edges"].append(
        {"from": "plan_approval", "to": "ghost_stage", "when": "request_changes", "max_loops": 1}
    )
    with pytest.raises(WorkflowDefinitionError):
        load_workflow(_write(tmp_path, data))


def test_declared_loopback_edge_requires_max_loops(tmp_path: Path, base_data: dict[str, Any]) -> None:
    data = copy.deepcopy(base_data)
    data["dependency_validation"]["loop_back_edges"].append(
        {"from": "build_execution", "to": "implementation_planning", "when": "uncertainty"}
    )
    with pytest.raises(WorkflowDefinitionError, match="max_loops"):
        load_workflow(_write(tmp_path, data))


def test_resolve_next_positional_and_declared(definition: Any) -> None:
    assert resolve_next_stage(definition, "research_proposal") == "research_approval"
    assert resolve_next_stage(definition, "research_execution") == "findings_review"
    assert resolve_next_stage(definition, "build_execution") == "completion"  # declared next
    assert resolve_next_stage(definition, "completion") is None


def test_resolve_next_decision_actions(definition: Any) -> None:
    assert resolve_next_stage(definition, "research_approval", action="approve") == "research_execution"
    assert resolve_next_stage(definition, "research_approval", action="cancel") == "completion"
    assert resolve_next_stage(definition, "plan_approval", action="approve") == "build_execution"
    assert resolve_next_stage(definition, "plan_approval", action="request_changes") == "implementation_planning"
    assert resolve_next_stage(definition, "plan_approval", action="decline") == "completion"


def test_resolve_next_decision_requires_action(definition: Any) -> None:
    with pytest.raises(WorkflowDefinitionError):
        resolve_next_stage(definition, "plan_approval")


def test_resolve_next_unknown_action_rejected(definition: Any) -> None:
    with pytest.raises(WorkflowDefinitionError):
        resolve_next_stage(definition, "research_approval", action="decline")


def test_check_cli_reports_alignment() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "breakdown", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "contracts: 8 aligned, 0 mismatches" in proc.stdout
    assert "produces coverage: full" in proc.stdout


def test_check_cli_fails_on_broken_definition(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("workflow_id: x\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "breakdown", "--check", "--workflow", str(broken)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "check failed" in proc.stdout
