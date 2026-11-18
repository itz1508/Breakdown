"""Offline evaluation runner (Phase 1).

Drives role operations against scripted fake backends and scores the
blocking-zero rules. Runs entirely offline: no network, no credentials,
no model SDK. Blocking zeros that require the Phase 2 safety boundary
are reported as not_run — never as passing.

Usage:  uv run --no-sync python evals/run.py --offline
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import sys
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from scorers import BlockingScoreboard

from breakdown.models import (
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
    RoleBackendRequest,
    RoleBackendResponse,
    RunRef,
    SourceCheckpoint,
    StageContext,
    TokenUsage,
)
from breakdown.roles import RoleOperationError, RoleToolkit
from breakdown.roles.auditor import Auditor
from breakdown.roles.builder import Builder
from breakdown.roles.coder import Coder
from breakdown.roles.planner import Planner
from breakdown.roles.researcher import Researcher

ROOT = Path(__file__).resolve().parent


def utcnow() -> datetime:
    return datetime.now(UTC)


class ScriptedBackend:
    """Fake RoleBackend returning one canned structured payload."""

    def __init__(self, payload: Mapping[str, Any] | None) -> None:
        self._payload = payload

    async def generate(self, request: RoleBackendRequest) -> RoleBackendResponse:
        if self._payload is None:
            raise RuntimeError(f"no scripted payload for {request.operation}")
        return RoleBackendResponse(
            structured_output=self._payload,
            text="",
            usage=TokenUsage(input_tokens=5, output_tokens=5),
            provider="eval-fake",
            model="eval-fake",
        )


class ScriptedCodingBackend:
    def __init__(self, result: ExecutionResult, observation: str = "applied the approved change") -> None:
        self._result = result
        self._observation = observation

    async def apply_task(self, request: Any) -> CodingBackendResult:
        return CodingBackendResult(
            execution_result=self._result,
            observation=self._observation,
            reported_changed_paths=(),
        )


def build_fixture_repo(base: Path) -> Path:
    src = base / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    tests = base / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_calc.py").write_text("def test_add() -> None:\n    assert 1 + 2 == 3\n", encoding="utf-8")
    (base / "README.md").write_text("# demo\n", encoding="utf-8")
    return base


def _checkpoint() -> SourceCheckpoint:
    return SourceCheckpoint(
        repository_identity="fixture-repo",
        commit_sha=None,
        file_hashes={"src/calc.py": "0" * 64},
        captured_at=utcnow(),
    )


def _processing_plan(expected: str) -> ProcessingPlan:
    return ProcessingPlan(
        objective="hand off to the next stage",
        input_refs=["research_proposal"],
        steps=["execute the approved scope"],
        expected_output_keys=[expected],
        completion_criteria=["outputs schema-valid"],
        evidence_required=["recorded observations"],
    )


def _proposal_output() -> ResearchProposalOutput:
    return ResearchProposalOutput.model_validate(PROFILES["valid_proposal"])


def _research_record() -> ResearchRecord:
    return ResearchRecord.model_validate(PROFILES["valid_research"]["research_record"])


PROFILES: Mapping[str, Mapping[str, Any]] = {
    "valid_proposal": {
        "exact_user_intent": "Add a subtract function to src/calc.py with a test.",
        "candidate_requirements": [
            {
                "requirement_id": "req-1",
                "text": "subtract function in src/calc.py",
                "origin": "user",
                "coverage": "not_covered",
                "evidence": "src/calc.py currently defines add only",
            }
        ],
        "research_questions": [
            {"question_id": "q-1", "text": "Which test conventions does the repo use?", "reason": "proposal scope"}
        ],
        "candidate_source_responsibilities": [
            {"requirement_refs": ["req-1"], "purpose": "implement subtract", "path": "src/calc.py"}
        ],
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
    },
    "proposal_uncertainty_without_question": {
        "exact_user_intent": "Add a subtract function to src/calc.py with a test.",
        "candidate_requirements": [
            {
                "requirement_id": "req-1",
                "text": "subtract function",
                "origin": "user",
                "coverage": "uncertainty",
                "evidence": "not yet inspected",
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
    },
    "valid_research": {
        "research_record": {
            "record_id": "rr-1",
            "resolved_questions": [
                {"question_id": "q-1", "answer": "tests live in tests/ and use pytest", "evidence_refs": ["ev-1"]}
            ],
            "unresolved_questions": [],
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "claim": "the repo uses pytest-style tests",
                    "source_identity": "fixture-repo",
                    "source_location": "tests/test_calc.py",
                    "accessed_at": "2026-11-17T00:00:00+00:00",
                    "status": "supported",
                }
            ],
            "contradictions": [
                {"topic": "naming", "positions": ["snake_case", "camelCase"], "evidence_refs": ["ev-1"]}
            ],
            "fixture_specifications": [],
        },
        "report_summary": "All approved questions addressed with provenance.",
        "research_todo": {"items": [{"question_id": "q-1", "status": "completed"}]},
    },
    "research_missing_question": {
        "research_record": {
            "record_id": "rr-2",
            "resolved_questions": [],
            "unresolved_questions": [],
            "evidence": [],
            "contradictions": [],
            "fixture_specifications": [],
        },
        "report_summary": "Nothing addressed.",
    },
    "valid_findings": {
        "classified_findings": [
            {
                "finding_id": "f-1",
                "requirement_ref": "req-1",
                "claim": "subtract is not implemented",
                "status": "supported",
                "decision_trace": [{"check": "source_inspected", "observation": "true", "evidence_ref": "ev-1"}],
                "criterion": "valid",
                "reason": "direct observation in src/calc.py",
            }
        ],
        "normalized_evidence": [{"evidence_ref": "ev-1", "normalized_form": "pytest convention confirmed"}],
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
    },
    "findings_drop_contradiction": {
        "classified_findings": [
            {
                "finding_id": "f-1",
                "requirement_ref": "req-1",
                "claim": "subtract is not implemented",
                "status": "supported",
                "decision_trace": [{"check": "source_inspected", "observation": "true", "evidence_ref": "ev-1"}],
                "criterion": "valid",
                "reason": "direct observation in src/calc.py",
            }
        ],
        "normalized_evidence": [],
        "reviewed_fixture_specifications": [],
        "reviewed_unresolved_questions": [],
        "contradictions_preserved": [],
        "implementation_planning_processing_plan": {
            "objective": "Create the authoritative ImplementationPlan",
            "input_refs": ["findings_review"],
            "steps": ["analyze planning gaps", "produce cohesive ordered build tasks"],
            "expected_output_keys": ["implementation_plan", "planning_review_result"],
            "completion_criteria": ["all requirements traced", "all tasks cohesive"],
            "evidence_required": ["reuse decisions with evidence"],
        },
    },
}


PLAN_PROFILE: Mapping[str, Any] = {
    "planning_gap_analysis": ["subtract is not implemented"],
    "planning_gap_resolutions": ["add subtract plus a test"],
    "implementation_plan": {
        "plan_id": "plan-1",
        "revision": 1,
        "objective": "Add subtract to src/calc.py with a test",
        "requirement_refs": ["req-1"],
        "source_checkpoint_ref": {"artifact_key": "source_checkpoint", "digest": "1" * 64},
        "technology_decisions": [],
        "tasks": [
            {
                "task_id": "task-1",
                "sequence": 1,
                "responsibility": "add subtract function with its test",
                "requirement_refs": ["req-1"],
                "target_paths": [
                    {"path": "src/calc.py", "disposition": "modify"},
                    {"path": "tests/test_calc.py", "disposition": "modify"},
                ],
                "source_evidence": ["f-1"],
                "capability_reuse": [],
                "reference_ids": [],
                "expected_result": "subtract(3, 2) == 1 and the test passes",
                "validation_steps": [
                    {
                        "step_id": "v-1",
                        "description": "run the demo test suite",
                        "command_or_observation": "pytest -q",
                        "expected": "all tests pass",
                    }
                ],
                "required_evidence": ["test output"],
            }
        ],
        "integration_checks": [],
        "success_criteria": [{"criterion": "subtract works and is tested", "measurable": True}],
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

CODE_ANALYSIS_PROFILE: Mapping[str, Any] = {
    "answer": "add is defined at src/calc.py:1; no subtract implementation exists",
    "file_evidence": [{"path": "src/calc.py", "locator": "line 1", "excerpt": "def add(a: int, b: int) -> int:"}],
    "criterion": "valid",
}


def _plan_overlap_profile() -> Mapping[str, Any]:
    profile = copy.deepcopy(dict(PLAN_PROFILE))
    plan = profile["implementation_plan"]
    assert isinstance(plan, dict)
    second = copy.deepcopy(plan["tasks"][0])
    second["task_id"] = "task-2"
    second["sequence"] = 2
    plan["tasks"].append(second)
    return profile


def profile_payload(profile: str) -> Mapping[str, Any] | None:
    if profile == "valid_plan":
        return PLAN_PROFILE
    if profile == "plan_overlap":
        return _plan_overlap_profile()
    if profile == "valid_code_analysis":
        return CODE_ANALYSIS_PROFILE
    if profile in ("build_completed", "build_failed"):
        return PLAN_PROFILE  # builder input derives from the plan; coding backend decides outcome
    return PROFILES.get(profile)


def build_input(operation: str) -> Any:
    request_text = "Add a subtract function to src/calc.py with a test."
    if operation == "create_research_proposal":
        return ResearchProposalInput(initial_request=InitialRequest(text=request_text, created_at=utcnow()))
    if operation == "execute_research":
        return ResearchExecutionInput(
            research_proposal=_proposal_output(),
            processing_plan=_processing_plan("research_response"),
            research_approval_ref={"artifact_key": "research_approval_record", "digest": "2" * 64},
            source_checkpoint=_checkpoint(),
        )
    if operation == "review_research_findings":
        return FindingsReviewInput(
            research_record=_research_record(),
            research_proposal=_proposal_output(),
            exact_user_intent=request_text,
            source_checkpoint=_checkpoint(),
        )
    if operation == "analyze_code":
        return CodeAnalysisRequest(question="Where is add defined?", scope_paths=("src/calc.py",))
    if operation == "create_implementation_plan":
        findings = tuple(
            ClassifiedFinding.model_validate(row) for row in PROFILES["valid_findings"]["classified_findings"]
        )
        return ImplementationPlanningInput(
            processing_plan=_processing_plan("implementation_plan"),
            classified_findings=findings,
            exact_user_intent=request_text,
            source_checkpoint=_checkpoint(),
        )
    if operation == "execute_build":
        plan_output = ImplementationPlanningOutput.model_validate(PLAN_PROFILE)
        return BuildExecutionInput(
            implementation_plan=plan_output.implementation_plan,
            frozen_plan_hash="3" * 64,
            preflight_result=PreflightResult(
                criterion=CriterionResult.VALID,
                criteria_results=({"name": "content_hash_match", "criterion": "valid", "evidence": "digest matches"},),
                checked_at=utcnow(),
            ),
            plan_approval_ref={"artifact_key": "plan_approval_record", "digest": "4" * 64},
            approval_hash="5" * 64,
            approved_plan_revision=1,
            approved_source_checkpoint=_checkpoint(),
            processing_plan=_processing_plan("task_results"),
        )
    raise KeyError(f"no input builder for operation {operation!r}")


def make_roles(fixture: Path, profile: str) -> dict[str, Any]:
    backend = ScriptedBackend(profile_payload(profile))
    coding_result = ExecutionResult.COMPLETED if profile == "build_completed" else ExecutionResult.FAILED
    return {
        "auditor": Auditor(backend=backend, tools=RoleToolkit(role="auditor", root=fixture)),
        "researcher": Researcher(backend=backend, tools=RoleToolkit(role="researcher", root=fixture)),
        "coder": Coder(backend=backend, tools=RoleToolkit(role="coder", root=fixture)),
        "planner": Planner(backend=backend, tools=RoleToolkit(role="planner", root=fixture)),
        "builder": Builder(backend=ScriptedCodingBackend(coding_result), sandbox_root=fixture / ".sandbox"),
    }


def run_case(case: Mapping[str, Any], fixture: Path, scoreboard: BlockingScoreboard) -> bool:
    role_name = str(case["role"])
    operation = str(case["operation"])
    profile = str(case["profile"])
    expect_valid = bool(case.get("expect", {}).get("output_valid", True))
    blocks = tuple(case.get("blocks", []))
    role = make_roles(fixture, profile)[role_name]
    context = StageContext(
        run=RunRef(
            run_id="run-eval",
            session_id="session-eval",
            definition_version=1,
            definition_digest="0" * 64,
        ),
        stage_id=str(case.get("stage", operation)),
    )
    input_value = build_input(operation)
    try:
        asyncio.run(getattr(role, operation)(input_value, context))
        accepted = True
        error = ""
    except (RoleOperationError, ValidationError) as exc:
        accepted = False
        error = str(exc).splitlines()[0][:200]
    ok = accepted == expect_valid
    label = "pass" if ok else "FAIL"
    print(f"[{label}] {role_name}.{operation} <- {profile}: accepted={accepted} expected_valid={expect_valid}")
    if not ok:
        if error:
            print(f"    rejection: {error}")
        for zero in blocks:
            scoreboard.violate(str(zero), f"{role_name}.{operation}/{profile} not handled as required")
    return ok


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted((ROOT / "cases").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for case in data.get("cases", []):
            case.setdefault("role", data["role"])
            cases.append(case)
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals")
    parser.add_argument(
        "--offline", action="store_true", required=True, help="Phase 1 supports offline evaluation only"
    )
    parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="breakdown-eval-") as temporary:
        fixture = build_fixture_repo(Path(temporary))
        scoreboard = BlockingScoreboard()
        cases = load_cases()
        passed = sum(run_case(case, fixture, scoreboard) for case in cases)
        print(f"\ncases: {passed}/{len(cases)} passed")
        print("blocking zeros:")
        failures = scoreboard.report()
    if failures or passed != len(cases):
        return 1
    print("offline evaluation: all scored blocking zeros hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
