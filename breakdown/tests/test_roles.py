"""Task 8 — role chain tests with offline fake backends + import boundary proof."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from breakdown.auditor.agent import Auditor
from breakdown.builder.agent import Builder
from breakdown.coder.agent import Coder
from breakdown.planner.agent import Planner
from breakdown.researcher.agent import Researcher, _build_baseline_map
from breakdown.shared.base import RoleOperationError
from breakdown.shared.models import (
    ArtifactRef,
    BuildExecutionInput,
    ClassifiedFinding,
    CodeAnalysisRequest,
    CodingBackendResult,
    CriterionResult,
    ExecutionResult,
    FindingsReviewInput,
    ImplementationPlanningInput,
    ImplementationPlanningOutput,
    InitialRequest,
    PreflightResult,
    ProcessingPlan,
    ResearchExecutionInput,
    ResearchProposalInput,
    ResearchProposalOutput,
    ResearchRecord,
    RunRef,
    SourceCheckpoint,
    StageContext,
)
from breakdown.system.tools.toolkit import RoleToolkit


def utcnow() -> datetime:
    return datetime.now(UTC)


def _context(stage_id: str) -> StageContext:
    return StageContext(
        run=RunRef(run_id="run-1", session_id="s-1", definition_version=1, definition_digest="0" * 64),
        stage_id=stage_id,
    )


def _checkpoint() -> SourceCheckpoint:
    return SourceCheckpoint(
        repository_identity="test-repo", commit_sha=None, file_hashes={"src/calc.py": "0" * 64}, captured_at=utcnow()
    )


def _processing_plan(expected: str) -> ProcessingPlan:
    return ProcessingPlan(
        objective="hand off",
        input_refs=["research_proposal"],
        steps=["execute approved scope"],
        expected_output_keys=[expected],
        completion_criteria=["schema-valid outputs"],
        evidence_required=["observations"],
    )


PROPOSAL_PAYLOAD: dict[str, Any] = {
    "exact_user_intent": "Add a subtract function to src/calc.py with a test.",
    "candidate_requirements": [
        {
            "requirement_id": "req-1",
            "text": "subtract function",
            "origin": "user",
            "coverage": "covered",
            "evidence": "stdlib arithmetic",
        }
    ],
    "research_questions": [{"question_id": "q-1", "text": "test conventions?", "reason": "scope"}],
    "candidate_source_responsibilities": [],
    "research_execution_processing_plan": {
        "objective": "Answer the approved research questions",
        "input_refs": ["research_proposal"],
        "steps": [
            "investigate each approved question",
            "record evidence with provenance",
        ],
        "expected_output_keys": [
            "research_response",
            "evidence_references",
            "resolved_questions",
            "unresolved_questions",
        ],
        "completion_criteria": ["every approved question addressed"],
        "evidence_required": ["provenance for material findings"],
    },
}

RESEARCH_PAYLOAD: dict[str, Any] = {
    "research_record": {
        "record_id": "rr-1",
        "resolved_questions": [{"question_id": "q-1", "answer": "pytest", "evidence_refs": ["ev-1"]}],
        "unresolved_questions": [],
        "evidence": [
            {
                "evidence_id": "ev-1",
                "claim": "repo uses pytest",
                "source_identity": "test-repo",
                "source_location": "tests/test_calc.py",
                "accessed_at": "2026-11-17T00:00:00+00:00",
                "status": "supported",
            }
        ],
        "contradictions": [{"topic": "naming", "positions": ["snake_case", "camelCase"], "evidence_refs": ["ev-1"]}],
        "fixture_specifications": [],
    },
    "report_summary": "addressed",
    "research_todo": {"items": [{"question_id": "q-1", "status": "completed"}]},
}

FINDINGS_PAYLOAD: dict[str, Any] = {
    "classified_findings": [
        {
            "finding_id": "f-1",
            "requirement_ref": "req-1",
            "claim": "subtract missing",
            "status": "supported",
            "decision_trace": [{"check": "inspected", "observation": "true", "evidence_ref": "ev-1"}],
            "criterion": "valid",
            "reason": "direct observation",
        }
    ],
    "normalized_evidence": [],
    "reviewed_fixture_specifications": [],
    "reviewed_unresolved_questions": [],
    "contradictions_preserved": [
        {"topic": "naming", "positions": ["snake_case", "camelCase"], "evidence_refs": ["ev-1"]}
    ],
    "implementation_planning_processing_plan": {
        "objective": "Create the authoritative ImplementationPlan",
        "input_refs": ["findings_review"],
        "steps": ["analyze planning gaps", "produce cohesive ordered build tasks"],
        "expected_output_keys": ["implementation_plan", "planning_review_result"],
        "completion_criteria": ["all requirements traced", "all tasks cohesive"],
        "evidence_required": ["reuse decisions with evidence"],
    },
}

PLAN_PAYLOAD: dict[str, Any] = {
    "planning_gap_analysis": ["subtract missing"],
    "planning_gap_resolutions": ["add subtract + test"],
    "implementation_plan": {
        "plan_id": "plan-1",
        "revision": 1,
        "objective": "Add subtract with a test",
        "requirement_refs": ["req-1"],
        "source_checkpoint_ref": {"artifact_key": "source_checkpoint", "digest": "1" * 64},
        "technology_decisions": [],
        "tasks": [
            {
                "task_id": "task-1",
                "sequence": 1,
                "responsibility": "add subtract with test",
                "requirement_refs": ["req-1"],
                "target_paths": [
                    {"path": "src/calc.py", "disposition": "modify"},
                    {"path": "tests/test_calc.py", "disposition": "modify"},
                ],
                "source_evidence": ["f-1"],
                "capability_reuse": [],
                "reference_ids": [],
                "expected_result": "src/calc.py defines subtract(a, b) and returns a - b",
                "validation_steps": [
                    {
                        "step_id": "v-1",
                        "description": "inspect the resulting source",
                        "command_or_observation": "read src/calc.py and verify subtract is defined and returns a - b",
                        "expected": "subtract is defined and returns a - b",
                        "kind": "observation",
                    }
                ],
                "required_evidence": ["test output"],
            }
        ],
        "integration_checks": [],
        "success_criteria": [{"criterion": "subtract tested", "measurable": True}],
    },
    "planning_review_result": {"cohesion": "valid", "notes": ""},
    "build_execution_processing_plan": {
        "objective": "Execute the approved BuildTasks in the sandbox",
        "input_refs": ["implementation_plan", "plan_approval_record"],
        "steps": ["apply each approved task sequentially", "validate against expected results"],
        "expected_output_keys": ["task_results", "validation_results", "build_result"],
        "completion_criteria": ["all tasks evidence-backed"],
        "evidence_required": ["check observations per task"],
    },
}


def _proposal_output() -> ResearchProposalOutput:
    return ResearchProposalOutput.model_validate(PROPOSAL_PAYLOAD)


def _research_record() -> ResearchRecord:
    return ResearchRecord.model_validate(RESEARCH_PAYLOAD["research_record"])


def _build_input(*, revision: int = 1, preflight: CriterionResult = CriterionResult.VALID) -> BuildExecutionInput:
    plan = ImplementationPlanningOutput.model_validate(PLAN_PAYLOAD).implementation_plan
    return BuildExecutionInput(
        implementation_plan=plan,
        frozen_plan_hash="3" * 64,
        preflight_result=PreflightResult(
            criterion=preflight,
            criteria_results=({"name": "content_hash_match", "criterion": preflight.value, "evidence": "ok"},),
            checked_at=utcnow(),
        ),
        plan_approval_ref=ArtifactRef(artifact_key="plan_approval_record", digest="4" * 64),
        approval_hash="5" * 64,
        approved_plan_revision=revision,
        approved_source_checkpoint=_checkpoint(),
        processing_plan=_processing_plan("task_results"),
    )


async def test_auditor_proposal_accepts_valid_output(fake_role_backend: Any, target_repo: Path) -> None:
    fake_role_backend.set_output("create_research_proposal", PROPOSAL_PAYLOAD)
    auditor = Auditor(backend=fake_role_backend, tools=RoleToolkit(role="auditor", root=target_repo))
    payload = ResearchProposalInput(initial_request=InitialRequest(text="Add subtract.", created_at=utcnow()))
    output = await auditor.create_research_proposal(payload, _context("research_proposal"))
    assert output.exact_user_intent


async def test_auditor_rejects_uncertainty_without_question(fake_role_backend: Any, target_repo: Path) -> None:
    bad = {
        "exact_user_intent": "x",
        "candidate_requirements": [
            {
                "requirement_id": "r1",
                "text": "t",
                "origin": "user",
                "coverage": "uncertainty",
                "evidence": "none yet",
            }
        ],
        "research_questions": [],
        "candidate_source_responsibilities": [],
        "research_execution_processing_plan": {
            "objective": "Answer the approved research questions",
            "input_refs": ["research_proposal"],
            "steps": ["investigate each approved question"],
            "expected_output_keys": ["research_response"],
            "completion_criteria": ["every approved question addressed"],
            "evidence_required": ["provenance for material findings"],
        },
    }
    fake_role_backend.set_output("create_research_proposal", bad)
    auditor = Auditor(backend=fake_role_backend, tools=RoleToolkit(role="auditor", root=target_repo))
    payload = ResearchProposalInput(initial_request=InitialRequest(text="x", created_at=utcnow()))
    with pytest.raises((RoleOperationError, ValidationError)):
        await auditor.create_research_proposal(payload, _context("research_proposal"))


async def test_auditor_findings_preserve_contradictions(fake_role_backend: Any, target_repo: Path) -> None:
    fake_role_backend.set_output("review_research_findings", FINDINGS_PAYLOAD)
    auditor = Auditor(backend=fake_role_backend, tools=RoleToolkit(role="auditor", root=target_repo))
    payload = FindingsReviewInput(
        research_record=_research_record(),
        research_proposal=_proposal_output(),
        exact_user_intent="x",
        source_checkpoint=_checkpoint(),
    )
    output = await auditor.review_research_findings(payload, _context("findings_review"))
    assert {contradiction.topic for contradiction in output.contradictions_preserved} == {"naming"}


async def test_auditor_rejects_unknown_requirement_references(
    fake_role_backend: Any, target_repo: Path
) -> None:
    invalid_finding = {
        **FINDINGS_PAYLOAD["classified_findings"][0],
        "requirement_ref": "requirement-not-in-proposal",
    }
    bad = {**FINDINGS_PAYLOAD, "classified_findings": [invalid_finding]}
    fake_role_backend.set_output("review_research_findings", bad)
    auditor = Auditor(backend=fake_role_backend, tools=RoleToolkit(role="auditor", root=target_repo))
    payload = FindingsReviewInput(
        research_record=_research_record(),
        research_proposal=_proposal_output(),
        exact_user_intent="x",
        source_checkpoint=_checkpoint(),
    )
    with pytest.raises(RoleOperationError, match="unknown requirements"):
        await auditor.review_research_findings(payload, _context("findings_review"))


async def test_auditor_rejects_changed_contradiction(
    fake_role_backend: Any, target_repo: Path
) -> None:
    changed = {
        **FINDINGS_PAYLOAD,
        "contradictions_preserved": [
            {"topic": "naming", "positions": ["snake_case", "PascalCase"], "evidence_refs": ["ev-1"]}
        ],
    }
    fake_role_backend.set_output("review_research_findings", changed)
    auditor = Auditor(backend=fake_role_backend, tools=RoleToolkit(role="auditor", root=target_repo))
    payload = FindingsReviewInput(
        research_record=_research_record(),
        research_proposal=_proposal_output(),
        exact_user_intent="x",
        source_checkpoint=_checkpoint(),
    )
    with pytest.raises(RoleOperationError, match="preserved exactly"):
        await auditor.review_research_findings(payload, _context("findings_review"))


async def test_auditor_rejects_finding_with_unknown_evidence(
    fake_role_backend: Any, target_repo: Path
) -> None:
    trace = [{**FINDINGS_PAYLOAD["classified_findings"][0]["decision_trace"][0], "evidence_ref": "missing"}]
    changed_finding = {**FINDINGS_PAYLOAD["classified_findings"][0], "decision_trace": trace}
    fake_role_backend.set_output(
        "review_research_findings",
        {**FINDINGS_PAYLOAD, "classified_findings": [changed_finding]},
    )
    auditor = Auditor(backend=fake_role_backend, tools=RoleToolkit(role="auditor", root=target_repo))
    payload = FindingsReviewInput(
        research_record=_research_record(),
        research_proposal=_proposal_output(),
        exact_user_intent="x",
        source_checkpoint=_checkpoint(),
    )
    with pytest.raises(RoleOperationError, match="unknown evidence"):
        await auditor.review_research_findings(payload, _context("findings_review"))


async def test_auditor_rejects_dropped_contradiction(fake_role_backend: Any, target_repo: Path) -> None:
    dropped = {**FINDINGS_PAYLOAD, "contradictions_preserved": []}
    fake_role_backend.set_output("review_research_findings", dropped)
    auditor = Auditor(backend=fake_role_backend, tools=RoleToolkit(role="auditor", root=target_repo))
    payload = FindingsReviewInput(
        research_record=_research_record(),
        research_proposal=_proposal_output(),
        exact_user_intent="x",
        source_checkpoint=_checkpoint(),
    )
    with pytest.raises(RoleOperationError):
        await auditor.review_research_findings(payload, _context("findings_review"))


async def test_researcher_addresses_every_question(fake_role_backend: Any, target_repo: Path) -> None:
    fake_role_backend.set_output("execute_research", RESEARCH_PAYLOAD)
    researcher = Researcher(backend=fake_role_backend, tools=RoleToolkit(role="researcher", root=target_repo))
    payload = ResearchExecutionInput(
        research_proposal=_proposal_output(),
        processing_plan=_processing_plan("research_response"),
        research_approval_ref=ArtifactRef(artifact_key="research_approval_record", digest="2" * 64),
        source_checkpoint=_checkpoint(),
    )
    output = await researcher.execute_research(payload, _context("research_execution"))
    assert output.research_record.resolved_questions


async def test_researcher_rejects_unaddressed_question(fake_role_backend: Any, target_repo: Path) -> None:
    empty_record = {
        "research_record": {
            "record_id": "rr-2",
            "resolved_questions": [],
            "unresolved_questions": [],
            "evidence": [],
            "contradictions": [],
            "fixture_specifications": [],
        },
        "report_summary": "nothing addressed",
    }
    fake_role_backend.set_output("execute_research", empty_record)
    researcher = Researcher(backend=fake_role_backend, tools=RoleToolkit(role="researcher", root=target_repo))
    payload = ResearchExecutionInput(
        research_proposal=_proposal_output(),
        processing_plan=_processing_plan("research_response"),
        research_approval_ref=ArtifactRef(artifact_key="research_approval_record", digest="2" * 64),
        source_checkpoint=_checkpoint(),
    )
    with pytest.raises(RoleOperationError):
        await researcher.execute_research(payload, _context("research_execution"))


async def test_researcher_rejects_unknown_resolved_evidence_reference(
    fake_role_backend: Any, target_repo: Path
) -> None:
    bad = {
        **RESEARCH_PAYLOAD,
        "research_record": {
            **RESEARCH_PAYLOAD["research_record"],
            "resolved_questions": [
                {"question_id": "q-1", "answer": "pytest", "evidence_refs": ["missing-evidence"]}
            ],
        },
    }
    fake_role_backend.set_output("execute_research", bad)
    researcher = Researcher(backend=fake_role_backend, tools=RoleToolkit(role="researcher", root=target_repo))
    payload = ResearchExecutionInput(
        research_proposal=_proposal_output(),
        processing_plan=_processing_plan("research_response"),
        research_approval_ref=ArtifactRef(artifact_key="research_approval_record", digest="2" * 64),
        source_checkpoint=_checkpoint(),
    )
    with pytest.raises(RoleOperationError, match="unknown evidence"):
        await researcher.execute_research(payload, _context("research_execution"))


async def test_researcher_rejects_normalized_evidence_provenance_drift(
    fake_role_backend: Any, target_repo: Path
) -> None:
    bad = {
        **RESEARCH_PAYLOAD,
        "research_record": {
            **RESEARCH_PAYLOAD["research_record"],
            "normalized_evidence": [
                {
                    "evidence_ref": "ev-1",
                    "normalized_form": "repo uses pytest",
                    "source_identity": "invented-repository",
                    "source_location": "tests/test_calc.py",
                    "provenance_preserved": True,
                }
            ],
        },
    }
    fake_role_backend.set_output("execute_research", bad)
    researcher = Researcher(backend=fake_role_backend, tools=RoleToolkit(role="researcher", root=target_repo))
    payload = ResearchExecutionInput(
        research_proposal=_proposal_output(),
        processing_plan=_processing_plan("research_response"),
        research_approval_ref=ArtifactRef(artifact_key="research_approval_record", digest="2" * 64),
        source_checkpoint=_checkpoint(),
    )
    with pytest.raises(RoleOperationError, match="changed source provenance"):
        await researcher.execute_research(payload, _context("research_execution"))


async def test_researcher_builds_baseline_map_and_normalizes_evidence(
    fake_role_backend: Any, target_repo: Path
) -> None:
    fake_role_backend.set_output("execute_research", RESEARCH_PAYLOAD)
    researcher = Researcher(backend=fake_role_backend, tools=RoleToolkit(role="researcher", root=target_repo))
    payload = ResearchExecutionInput(
        research_proposal=_proposal_output(),
        processing_plan=_processing_plan("research_response"),
        research_approval_ref=ArtifactRef(artifact_key="research_approval_record", digest="2" * 64),
        source_checkpoint=_checkpoint(),
    )
    output = await researcher.execute_research(payload, _context("research_execution"))
    record = output.research_record
    assert record.baseline_map is not None
    assert record.baseline_map.repository_identity == "test-repo"
    assert len(record.baseline_map.entries) >= 1
    assert record.baseline_map.entries[0].path == "src/calc.py"
    assert record.baseline_map.entries[0].category == "source"
    assert record.baseline_map.entries[0].exports_status == "complete"

    assert len(record.normalized_evidence) >= 1
    norm = record.normalized_evidence[0]
    assert norm.evidence_ref == "ev-1"
    assert norm.source_identity == "test-repo"
    assert norm.source_location == "tests/test_calc.py"
    assert norm.provenance_preserved is True



def test_researcher_baseline_map_marks_invalid_python_source(target_repo: Path) -> None:
    broken_path = target_repo / "src" / "broken.py"
    broken_path.write_text("def unfinished(", encoding="utf-8")
    checkpoint = _checkpoint().model_copy(update={"file_hashes": {"src/broken.py": "b" * 64}})

    baseline_map = _build_baseline_map(checkpoint, target_repo)

    entry = baseline_map.entries[0]
    assert entry.path == "src/broken.py"
    assert entry.exports == ()
    assert entry.exports_status == "syntax_invalid"



def test_researcher_baseline_map_rejects_paths_outside_repository(target_repo: Path) -> None:
    outside_file = target_repo.parent / "outside.py"
    outside_file.write_text("class OutsideRepository: pass", encoding="utf-8")
    checkpoint = _checkpoint().model_copy(update={"file_hashes": {"../outside.py": "c" * 64}})

    baseline_map = _build_baseline_map(checkpoint, target_repo)

    entry = baseline_map.entries[0]
    assert entry.exports == ()
    assert entry.exports_status == "out_of_scope"


async def test_researcher_rejects_missing_provenance(fake_role_backend: Any, target_repo: Path) -> None:
    bad_payload = {
        "research_record": {
            "record_id": "rr-bad",
            "resolved_questions": [{"question_id": "q-1", "answer": "pytest", "evidence_refs": ["ev-1"]}],
            "unresolved_questions": [],
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "claim": "repo uses pytest",
                    "source_identity": "",  # missing provenance
                    "source_location": "",
                    "accessed_at": "2026-11-17T00:00:00+00:00",
                    "status": "supported",
                }
            ],
            "contradictions": [],
            "fixture_specifications": [],
        },
        "report_summary": "addressed",
        "research_todo": {"items": [{"question_id": "q-1", "status": "completed"}]},
    }
    fake_role_backend.set_output("execute_research", bad_payload)
    researcher = Researcher(backend=fake_role_backend, tools=RoleToolkit(role="researcher", root=target_repo))
    payload = ResearchExecutionInput(
        research_proposal=_proposal_output(),
        processing_plan=_processing_plan("research_response"),
        research_approval_ref=ArtifactRef(artifact_key="research_approval_record", digest="2" * 64),
        source_checkpoint=_checkpoint(),
    )
    with pytest.raises(RoleOperationError):
        await researcher.execute_research(payload, _context("research_execution"))


async def test_planner_produces_authoritative_plan(fake_role_backend: Any, target_repo: Path) -> None:
    fake_role_backend.set_output("create_implementation_plan", PLAN_PAYLOAD)
    planner = Planner(backend=fake_role_backend, tools=RoleToolkit(role="planner", root=target_repo))
    payload = ImplementationPlanningInput(
        processing_plan=_processing_plan("implementation_plan"),
        classified_findings=tuple(
            ClassifiedFinding.model_validate(row) for row in FINDINGS_PAYLOAD["classified_findings"]
        ),
        exact_user_intent="x",
        source_checkpoint=_checkpoint(),
    )
    output = await planner.create_implementation_plan(payload, _context("implementation_planning"))
    assert output.implementation_plan.tasks[0].target_paths


def test_planner_overlap_rejected_by_model() -> None:
    first = PLAN_PAYLOAD["implementation_plan"]["tasks"][0]
    second = {**first, "task_id": "task-2", "sequence": 2, "target_paths": list(first["target_paths"])}
    payload = {
        **PLAN_PAYLOAD,
        "implementation_plan": {**PLAN_PAYLOAD["implementation_plan"], "tasks": [first, second]},
    }
    with pytest.raises(ValidationError):
        ImplementationPlanningOutput.model_validate(payload)


async def test_planner_rejects_requirement_not_backed_by_reviewed_finding(
    fake_role_backend: Any, target_repo: Path
) -> None:
    invalid_plan = {
        **PLAN_PAYLOAD,
        "implementation_plan": {
            **PLAN_PAYLOAD["implementation_plan"],
            "requirement_refs": ["req-1", "requirement-not-reviewed"],
        },
    }
    fake_role_backend.set_output("create_implementation_plan", invalid_plan)
    planner = Planner(backend=fake_role_backend, tools=RoleToolkit(role="planner", root=target_repo))
    payload = ImplementationPlanningInput(
        processing_plan=_processing_plan("implementation_plan"),
        classified_findings=tuple(
            ClassifiedFinding.model_validate(row) for row in FINDINGS_PAYLOAD["classified_findings"]
        ),
        exact_user_intent="x",
        source_checkpoint=_checkpoint(),
    )
    with pytest.raises(RoleOperationError, match="without reviewed findings"):
        await planner.create_implementation_plan(payload, _context("implementation_planning"))


async def test_builder_completed_prepares_sync(fake_coding_backend: Any, tmp_path: Path) -> None:
    builder = Builder(backend=fake_coding_backend, sandbox_root=tmp_path / "sandbox")
    output = await builder.execute_build(_build_input(), _context("build_execution"))
    assert output.synchronization_prepared is True
    assert all(result.criterion is CriterionResult.VALID for result in output.task_results)


async def test_builder_failure_stops_and_is_not_valid(fake_coding_backend: Any, tmp_path: Path) -> None:
    fake_coding_backend.result = CodingBackendResult(
        execution_result=ExecutionResult.FAILED, observation="check failed", reported_changed_paths=()
    )
    builder = Builder(backend=fake_coding_backend, sandbox_root=tmp_path / "sandbox")
    output = await builder.execute_build(_build_input(), _context("build_execution"))
    assert output.synchronization_prepared is False
    assert output.task_results[0].criterion is CriterionResult.NOT_VALID
    assert output.task_results[0].attempts == 3  # initial attempt + 2 corrections


async def test_builder_rejects_stale_approval_revision(fake_coding_backend: Any, tmp_path: Path) -> None:
    builder = Builder(backend=fake_coding_backend, sandbox_root=tmp_path / "sandbox")
    with pytest.raises(RoleOperationError):
        await builder.execute_build(_build_input(revision=99), _context("build_execution"))


def test_builder_input_requires_valid_preflight() -> None:
    with pytest.raises(ValidationError):
        _build_input(preflight=CriterionResult.UNCERTAINTY)


async def test_coder_returns_file_evidence(fake_role_backend: Any, target_repo: Path) -> None:
    fake_role_backend.set_output(
        "analyze_code",
        {
            "answer": "add defined at src/calc.py:1",
            "file_evidence": [{"path": "src/calc.py", "locator": "line 1", "excerpt": "def add"}],
            "criterion": "valid",
        },
    )
    coder = Coder(backend=fake_role_backend, tools=RoleToolkit(role="coder", root=target_repo))
    request = CodeAnalysisRequest(question="where is add?", scope_paths=("src/calc.py",))
    output = await coder.analyze_code(request, _context("findings_review"))
    assert output.file_evidence
    assert output.criterion is CriterionResult.VALID


async def test_coder_rejects_evidence_outside_requested_scope(
    fake_role_backend: Any, target_repo: Path
) -> None:
    fake_role_backend.set_output(
        "analyze_code",
        {
            "answer": "claim from another file",
            "file_evidence": [{"path": "README.md", "locator": "line 1", "excerpt": "# project"}],
            "criterion": "valid",
        },
    )
    coder = Coder(backend=fake_role_backend, tools=RoleToolkit(role="coder", root=target_repo))
    request = CodeAnalysisRequest(question="where is add?", scope_paths=("src/calc.py",))
    with pytest.raises(RoleOperationError, match="outside requested scope"):
        await coder.analyze_code(request, _context("findings_review"))


async def test_coder_rejects_invented_source_excerpt(
    fake_role_backend: Any, target_repo: Path
) -> None:
    fake_role_backend.set_output(
        "analyze_code",
        {
            "answer": "add is at line 1",
            "file_evidence": [
                {"path": "src/calc.py", "locator": "line 1", "excerpt": "def fabricated(): pass"}
            ],
            "criterion": "valid",
        },
    )
    coder = Coder(backend=fake_role_backend, tools=RoleToolkit(role="coder", root=target_repo))
    request = CodeAnalysisRequest(question="where is add?", scope_paths=("src",))
    with pytest.raises(RoleOperationError, match="does not occur"):
        await coder.analyze_code(request, _context("findings_review"))


async def test_coder_accepts_evidence_under_requested_directory(
    fake_role_backend: Any, target_repo: Path
) -> None:
    fake_role_backend.set_output(
        "analyze_code",
        {
            "answer": "add is defined in src/calc.py",
            "file_evidence": [
                {"path": "src/calc.py", "locator": "line 1", "excerpt": "def add"}
            ],
            "criterion": "valid",
        },
    )
    coder = Coder(backend=fake_role_backend, tools=RoleToolkit(role="coder", root=target_repo))
    request = CodeAnalysisRequest(question="where is add?", scope_paths=("src",))
    output = await coder.analyze_code(request, _context("findings_review"))
    assert output.file_evidence[0].path == "src/calc.py"


def test_roles_import_only_shared_layers() -> None:
    package_root = Path(__file__).resolve().parents[1]
    agent_files = [
        package_root / "auditor" / "agent.py",
        package_root / "researcher" / "agent.py",
        package_root / "coder" / "agent.py",
        package_root / "planner" / "agent.py",
        package_root / "builder" / "agent.py",
    ]
    allowed = ("breakdown.agents.", "breakdown.shared.", "breakdown.system.tools.")
    for path in agent_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("breakdown."):
                assert node.module.startswith(allowed), (
                    f"{path.name} imports outside shared agent-support/system tools: {node.module}"
                )
        if path.parent.name == "builder":
            assert "breakdown.shared.model_loop" not in path.read_text(encoding="utf-8")
