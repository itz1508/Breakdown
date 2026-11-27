"""Task 5 — canonical tool tests: good and bad rows.

Runtime operations (source_checkpoint, plan freeze/preflight, approval
hashing, synchronization) must never appear in the model-callable registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from breakdown.system.tools.tools import (
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


def test_registry_exposes_model_callable_tools() -> None:
    # D36: three read-only memory tools join source tools; semantic_search added for Researcher; D43: web_search.
    assert set(TOOLS) == {
        "capability_inspect",
        "source_search",
        "source_read",
        "memory_list",
        "memory_read",
        "memory_search",
        "semantic_search",
        "web_search",
    }
    for forbidden in (
        "proposal_create",
        "plan_freeze",
        "plan_preflight",
        "source_checkpoint",
        "memory_lookup",
        "memory_write",  # runtime-only write discipline (D36): no model-callable write tool
    ):
        assert forbidden not in TOOLS


def test_role_allowlists_match_matrix() -> None:
    assert ROLE_TOOL_ALLOWLIST["builder"] == ()  # builder never reads or writes memory
    assert set(ROLE_TOOL_ALLOWLIST["researcher"]) == {
        "source_search",
        "source_read",
        "memory_list",
        "memory_read",
        "memory_search",
        "semantic_search",
        "web_search",
    }
    assert "capability_inspect" in ROLE_TOOL_ALLOWLIST["auditor"]
    assert "semantic_search" in ROLE_TOOL_ALLOWLIST["auditor"]
    for role in ("auditor", "coder", "planner"):
        assert {"memory_list", "memory_read", "memory_search"} <= set(ROLE_TOOL_ALLOWLIST[role])


def test_tool_definitions_carry_schemas() -> None:
    definitions = tool_definitions()
    assert {definition["name"] for definition in definitions} == set(TOOLS)
    assert all("parameters" in definition for definition in definitions)


def test_semantic_search_offline_fallback(repo: Path) -> None:
    from breakdown.semantic_search import SemanticSearchRequest, semantic_search

    report = semantic_search(SemanticSearchRequest(query="calc add"), root=repo)
    assert report.mode == "lexical_fallback"
    assert len(report.matches) >= 1
    assert report.matches[0].path == "src/calc.py"
    assert "def add" in report.matches[0].snippet


def test_semantic_search_dispatch(repo: Path) -> None:
    report = dispatch_tool("semantic_search", {"query": "return a + b"}, root=repo)
    assert len(report.matches) >= 1
    assert report.matches[0].path == "src/calc.py"


def test_web_search_enforces_domain_and_use_limits(repo: Path) -> None:
    from breakdown.tools import ToolNotAuthorized, WebSearchRequest, web_search

    # Domain in allowed_domains succeeds
    res = web_search(WebSearchRequest(query="site:python.org pytest", allowed_domains=("python.org",)))
    assert res.uses_consumed <= 5
    assert len(res.results) >= 1
    assert res.results[0].domain == "python.org"
    assert res.search_cost_tokens > 0

    # Domain not in allowed_domains raises ToolNotAuthorized
    with pytest.raises(ToolNotAuthorized):
        web_search(WebSearchRequest(query="site:untrusted.com exploit", allowed_domains=("python.org",)))


def test_web_search_offline_fallback_or_error(repo: Path) -> None:
    from breakdown.tools import WebSearchRequest, web_search

    # Offline query without specific domain gracefully falls back
    res = web_search(WebSearchRequest(query="pytest fixture patterns"))
    assert res.uses_consumed >= 1
    assert len(res.results) >= 1
    assert res.search_cost_tokens > 0


def test_web_search_encrypted_content_rejected(repo: Path) -> None:
    from breakdown.tools import WebSearchRequest, web_search

    with pytest.raises(ValueError, match="encrypted or binary"):
        web_search(WebSearchRequest(query="download encrypted blob"))


def test_web_search_dispatch_and_toolkit(repo: Path) -> None:
    from breakdown.system.tools.toolkit import RoleToolkit

    # Test via dispatch_tool
    dispatched = dispatch_tool("web_search", {"query": "pytest test runner"}, root=repo)
    assert dispatched.uses_consumed >= 1
    assert len(dispatched.results) >= 1

    # Test via Researcher RoleToolkit
    toolkit = RoleToolkit(role="researcher", root=repo)
    assert "web_search" in toolkit.allowed_names()
    result = toolkit.call("web_search", {"query": "site:python.org unittest", "allowed_domains": ["python.org"]})
    assert result.results[0].domain == "python.org"
