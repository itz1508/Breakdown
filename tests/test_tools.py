"""Task 5 — canonical tool tests: good and bad rows.

Runtime operations (source_checkpoint, plan freeze/preflight, approval
hashing, synchronization) must never appear in the model-callable registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from breakdown.tools import (
    ROLE_TOOL_ALLOWLIST,
    TOOLS,
    CapabilityInspectRequest,
    SourceReadRequest,
    SourceSearchRequest,
    ToolInputNotValid,
    ToolNotAuthorized,
    capability_inspect,
    dispatch_tool,
    source_read,
    source_search,
    tool_definitions,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("SECRET=2\n", encoding="utf-8")
    return tmp_path


def test_capability_inspect_installed_distribution() -> None:
    report = capability_inspect(CapabilityInspectRequest(distribution="pydantic"))
    assert report.installed is True
    assert report.version


def test_capability_inspect_unknown_distribution_never_imports() -> None:
    report = capability_inspect(CapabilityInspectRequest(distribution="no-such-distribution-xyz"))
    assert report.installed is False
    assert report.version is None


def test_source_search_finds_match(repo: Path) -> None:
    report = source_search(SourceSearchRequest(pattern=r"def add"), root=repo)
    assert any(match.path == "src/calc.py" for match in report.matches)


def test_source_search_invalid_pattern_rejected(repo: Path) -> None:
    with pytest.raises(ToolInputNotValid):
        source_search(SourceSearchRequest(pattern="("), root=repo)


def test_source_read_returns_file(repo: Path) -> None:
    result = source_read(SourceReadRequest(path="src/calc.py"), root=repo)
    assert "def add" in result.content
    assert result.truncated is False


@pytest.mark.parametrize("path", ["../outside.py", "/abs/path.py", ".env", ".env.local"])
def test_source_read_denies_escapes_and_secrets(repo: Path, path: str) -> None:
    with pytest.raises(ToolNotAuthorized):
        source_read(SourceReadRequest(path=path), root=repo)


def test_dispatch_validates_payload(repo: Path) -> None:
    with pytest.raises(ToolInputNotValid):
        dispatch_tool("source_read", {"path": ""}, root=repo)


def test_dispatch_unknown_tool_denied(repo: Path) -> None:
    with pytest.raises(ToolNotAuthorized):
        dispatch_tool("artifact_write", {}, root=repo)


def test_registry_exposes_exactly_three_model_callable_tools() -> None:
    assert set(TOOLS) == {"capability_inspect", "source_search", "source_read"}
    for forbidden in (
        "proposal_create",
        "plan_freeze",
        "plan_preflight",
        "source_checkpoint",
        "memory_lookup",
    ):
        assert forbidden not in TOOLS


def test_role_allowlists_match_matrix() -> None:
    assert ROLE_TOOL_ALLOWLIST["builder"] == ()
    assert set(ROLE_TOOL_ALLOWLIST["researcher"]) == {"source_search", "source_read"}
    assert "capability_inspect" in ROLE_TOOL_ALLOWLIST["auditor"]


def test_tool_definitions_carry_schemas() -> None:
    definitions = tool_definitions()
    assert {definition["name"] for definition in definitions} == set(TOOLS)
    assert all("parameters" in definition for definition in definitions)
