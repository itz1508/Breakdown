"""Shared test fixtures: offline fake backends and a tiny target repository.

Phase 1 runs entirely offline. Fake backends conform structurally to the
RoleBackend / CodingBackend protocols defined in ``breakdown.contracts``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from breakdown.models import (
    CodingBackendRequest,
    CodingBackendResult,
    ExecutionResult,
    RoleBackendRequest,
    RoleBackendResponse,
    TokenUsage,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def make_task_payload(
    task_id: str = "task-1",
    sequence: int = 1,
    paths: tuple[str, ...] = ("src/calc.py",),
    depends_on: tuple[str, ...] = (),
) -> dict[str, Any]:
    """A minimal valid BuildTask payload for tests and evals."""
    return {
        "task_id": task_id,
        "sequence": sequence,
        "responsibility": "add subtract function with test",
        "requirement_refs": ["req-1"],
        "target_paths": [{"path": path, "disposition": "modify"} for path in paths],
        "source_evidence": ["finding-1"],
        "capability_reuse": [],
        "reference_ids": [],
        "expected_result": "subtract(3, 2) == 1",
        "validation_steps": [
            {
                "step_id": "v1",
                "description": "run the demo test suite",
                "command_or_observation": "pytest -q",
                "expected": "all tests pass",
            }
        ],
        "required_evidence": ["test output"],
        "depends_on": list(depends_on),
    }


class FakeRoleBackend:
    """Scripted offline backend returning canned structured output per operation."""

    def __init__(self, scripted: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.scripted: dict[str, Mapping[str, Any]] = dict(scripted or {})
        self.requests: list[RoleBackendRequest] = []

    def set_output(self, operation: str, structured: Mapping[str, Any]) -> None:
        self.scripted[operation] = structured

    async def generate(self, request: RoleBackendRequest) -> RoleBackendResponse:
        self.requests.append(request)
        structured = self.scripted.get(request.operation)
        if structured is None:
            raise RuntimeError(f"no scripted output for operation {request.operation!r}")
        return RoleBackendResponse(
            structured_output=structured,
            text="",
            usage=TokenUsage(input_tokens=10, output_tokens=20, tool_calls=0),
            provider="fake",
            model="fake-offline",
        )


class FakeCodingBackend:
    """Scripted coding backend for sandbox task application."""

    def __init__(self, result: CodingBackendResult | None = None) -> None:
        self.result = result or CodingBackendResult(
            execution_result=ExecutionResult.COMPLETED,
            observation="applied the approved change",
            reported_changed_paths=(),
        )
        self.requests: list[CodingBackendRequest] = []

    async def apply_task(self, request: CodingBackendRequest) -> CodingBackendResult:
        self.requests.append(request)
        return self.result


@pytest.fixture
def fake_role_backend() -> FakeRoleBackend:
    return FakeRoleBackend()


@pytest.fixture
def fake_coding_backend() -> FakeCodingBackend:
    return FakeCodingBackend()


@pytest.fixture
def target_repo(tmp_path: Path) -> Path:
    """Tiny demonstration repository: src/calc.py with an add function + test."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add() -> None:\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    return tmp_path
