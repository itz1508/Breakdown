"""Task F4/F5 — bootstrap wiring and fail-fast binding validation tests."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from typing import Any

import pytest
from breakdown.shared.models import Settings
from breakdown.system.runtime.bindings import BindingNotValid
from breakdown.system.runtime.bootstrap import bootstrap
from breakdown.system.tools.toolkit import RoleToolkit
from breakdown.system.tools.tools import ToolNotAuthorized

REPO_ROOT = Path(__file__).resolve().parents[3]


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
    assert set(app.roles) == {"auditor", "researcher", "coder", "planner", "builder"}
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


class _RecordingBackend:
    """Wraps a demo backend and records which operations it served."""

    def __init__(self, label: str) -> None:
        from breakdown.system.runtime.demo import OfflineDemoRoleBackend

        self.label = label
        self.operations: list[str] = []
        self._inner = OfflineDemoRoleBackend("record the demo change")

    async def generate(self, request: Any) -> Any:
        self.operations.append(request.operation)
        return await self._inner.generate(request)


def test_build_runtime_routes_per_role_backends(target_repo: Path) -> None:
    from breakdown.system.runtime.bootstrap import build_runtime
    from breakdown.system.runtime.demo import OfflineDemoCodingBackend

    auditor_backend = _RecordingBackend("auditor-tier")
    fallback_backend = _RecordingBackend("worker-tier")
    runtime = build_runtime(
        _settings(target_repo),
        role_backends={"auditor": auditor_backend},
        role_backend=fallback_backend,
        coding_backend=OfflineDemoCodingBackend("record the demo change"),
    )
    try:
        record = runtime.engine.start_run("record the demo change", user_identity="u")
        record = runtime.engine.advance(record.run_id)
        assert record.current_stage == "research_approval"
        assert auditor_backend.operations == ["create_research_proposal"]
        assert fallback_backend.operations == []
        runtime.engine.record_decision(record.run_id, "approve", user_identity="u")
        record = runtime.engine.advance(record.run_id)
        assert record.current_stage == "plan_approval"
        assert auditor_backend.operations == ["create_research_proposal", "review_research_findings"]
        assert fallback_backend.operations == ["execute_research", "create_implementation_plan"]
    finally:
        runtime.lock.release()


def test_build_runtime_missing_role_backend_raises(target_repo: Path) -> None:
    from breakdown.system.runtime.bootstrap import BootstrapError, build_runtime
    from breakdown.system.runtime.demo import OfflineDemoCodingBackend

    runtime = build_runtime(
        _settings(target_repo),
        role_backend=None,
        coding_backend=OfflineDemoCodingBackend("x"),
    )
    try:
        record = runtime.engine.start_run("request", user_identity="u")
        with pytest.raises(BootstrapError, match="no backend available"):
            runtime.engine.advance(record.run_id)
    finally:
        runtime.lock.release()


def _live_binding_payload(role: str, operations: list[str], binding_id: str) -> dict[str, Any]:
    return {
        "binding_id": binding_id,
        "role": role,
        "implementation": "openai_compatible",
        "package_name": "openai",
        "installed_version": importlib.metadata.version("openai"),
        "evaluation_ref": {"artifact_key": "backend_evaluation", "digest": "a" * 64},
        "evaluation_status": "completed",
        "permitted_operations": operations,
        "required_capabilities": ["structured_output", "tool_calls", "tool_loop", "usage_data"],
        "live_required": True,
        "live_status": "valid",
        "binding_revision": 1,
        "approved_at": "2026-11-19T00:00:00+00:00",
    }


def _write_bindings(tmp_path: Path, bindings: list[dict[str, Any]]) -> Path:
    path = tmp_path / "bindings.json"
    path.write_text(json.dumps(bindings), encoding="utf-8")
    return path


def _full_bindings() -> list[dict[str, Any]]:
    return [
        _live_binding_payload("auditor", ["create_research_proposal", "review_research_findings"], "b-aud"),
        _live_binding_payload("researcher", ["execute_research"], "b-res"),
        _live_binding_payload("planner", ["create_implementation_plan"], "b-pln"),
    ]


def test_binding_coverage_requires_every_role_stage(target_repo: Path, tmp_path: Path) -> None:
    from breakdown.system.runtime.bootstrap import build_runtime
    from breakdown.system.runtime.demo import OfflineDemoCodingBackend, OfflineDemoRoleBackend

    bindings = _full_bindings()[:1]  # auditor only -> researcher/planner unbound
    settings = _settings(target_repo, _write_bindings(tmp_path, bindings))
    with pytest.raises(BindingNotValid, match="no backend binding"):
        build_runtime(
            settings,
            role_backend=OfflineDemoRoleBackend("x"),
            coding_backend=OfflineDemoCodingBackend("x"),
        )


def test_binding_coverage_requires_permitted_operations(target_repo: Path, tmp_path: Path) -> None:
    from breakdown.system.runtime.bootstrap import build_runtime
    from breakdown.system.runtime.demo import OfflineDemoCodingBackend, OfflineDemoRoleBackend

    bindings = _full_bindings()
    bindings[0]["permitted_operations"] = ["create_research_proposal"]  # drops review_research_findings
    settings = _settings(target_repo, _write_bindings(tmp_path, bindings))
    with pytest.raises(BindingNotValid, match="permitted_operations missing"):
        build_runtime(
            settings,
            role_backend=OfflineDemoRoleBackend("x"),
            coding_backend=OfflineDemoCodingBackend("x"),
        )


def test_binding_coverage_passes_with_complete_bindings(target_repo: Path, tmp_path: Path) -> None:
    from breakdown.system.runtime.bootstrap import build_runtime
    from breakdown.system.runtime.demo import OfflineDemoCodingBackend, OfflineDemoRoleBackend

    settings = _settings(target_repo, _write_bindings(tmp_path, _full_bindings()))
    runtime = build_runtime(
        settings,
        role_backend=OfflineDemoRoleBackend("x"),
        coding_backend=OfflineDemoCodingBackend("x"),
    )
    assert len(runtime.bindings.all()) == 3
    runtime.lock.release()
