"""Task F4/F5 — bootstrap wiring and fail-fast binding validation tests."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from typing import Any

import pytest

from breakdown.bindings import BindingNotValid
from breakdown.bootstrap import bootstrap
from breakdown.models import Settings
from breakdown.roles import RoleToolkit
from breakdown.tools import ToolNotAuthorized

REPO_ROOT = Path(__file__).resolve().parent.parent


def _settings(target_repo: Path, bindings_path: Path | None = None) -> Settings:
    return Settings(
        workflow_path=REPO_ROOT / "breakdown.yaml",
        target_repo=target_repo,
        backend_bindings_path=bindings_path,
    )


def test_bootstrap_builds_aligned_application(
    fake_role_backend: Any, fake_coding_backend: Any, target_repo: Path, tmp_path: Path
) -> None:
    app = bootstrap(
        _settings(target_repo),
        role_backend=fake_role_backend,
        coding_backend=fake_coding_backend,
        sandbox_root=tmp_path / "sandbox",
    )
    assert app.definition.workflow_id == "oneshot.breakdown"
    assert len(app.contracts) == 8
    assert set(app.roles) == {"auditor", "researcher", "planner", "builder"}
    assert app.bindings.all() == ()


def _binding_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "binding_id": "b1",
        "role": "auditor",
        "implementation": "fake_offline",
        "package_name": "pydantic",
        "installed_version": importlib.metadata.version("pydantic"),
        "evaluation_ref": {"artifact_key": "backend_evaluation", "digest": "a" * 64},
        "evaluation_status": "completed",
        "permitted_operations": ["create_research_proposal", "review_research_findings"],
    }
    payload.update(overrides)
    return payload


def test_bootstrap_rejects_invalid_binding_file(
    fake_role_backend: Any, fake_coding_backend: Any, target_repo: Path, tmp_path: Path
) -> None:
    bindings_file = tmp_path / "bindings.json"
    stale = _binding_payload(installed_version="0.0.1-stale")
    bindings_file.write_text(json.dumps([stale]), encoding="utf-8")
    with pytest.raises(BindingNotValid):
        bootstrap(
            _settings(target_repo, bindings_file),
            role_backend=fake_role_backend,
            coding_backend=fake_coding_backend,
            sandbox_root=tmp_path / "sandbox",
        )


def test_bootstrap_accepts_valid_binding_file(
    fake_role_backend: Any, fake_coding_backend: Any, target_repo: Path, tmp_path: Path
) -> None:
    bindings_file = tmp_path / "bindings.json"
    bindings_file.write_text(json.dumps([_binding_payload()]), encoding="utf-8")
    app = bootstrap(
        _settings(target_repo, bindings_file),
        role_backend=fake_role_backend,
        coding_backend=fake_coding_backend,
        sandbox_root=tmp_path / "sandbox",
    )
    assert app.bindings.for_role("auditor") is not None


def test_role_toolkit_enforces_allowlists(target_repo: Path) -> None:
    builder_kit = RoleToolkit(role="builder", root=target_repo)
    with pytest.raises(ToolNotAuthorized):
        builder_kit.call("source_read", {"path": "README.md"})

    researcher_kit = RoleToolkit(role="researcher", root=target_repo)
    with pytest.raises(ToolNotAuthorized):
        researcher_kit.call("capability_inspect", {"distribution": "pydantic"})

    auditor_kit = RoleToolkit(role="auditor", root=target_repo)
    result = auditor_kit.call("source_read", {"path": "README.md"})
    assert "demo" in result.content
