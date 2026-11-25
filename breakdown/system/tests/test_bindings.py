"""Task 9 — backend binding records and invalidation rules.

A binding is invalid when: package version changed, evaluation is missing
or not completed, no operation is permitted, or live behavior is required
but remains not_run.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

import pytest
from breakdown.shared.models import BackendBinding
from breakdown.system.runtime.bindings import BackendBindingStore, BindingNotValid, validate_binding

def _binding(**overrides: Any) -> BackendBinding:
    payload: dict[str, Any] = {
        "binding_id": "binding-auditor-1",
        "role": "auditor",
        "implementation": "fake_offline",
        "package_name": "pydantic",
        "installed_version": importlib.metadata.version("pydantic"),
        "evaluation_ref": {"artifact_key": "backend_evaluation", "digest": "a" * 64},
        "evaluation_status": "completed",
        "permitted_operations": ["create_research_proposal", "review_research_findings"],
        "required_capabilities": ["structured_output"],
        "live_required": False,
        "binding_revision": 1,
        "approved_at": "2026-11-17T00:00:00+00:00",
    }
    payload.update(overrides)
    return BackendBinding.model_validate(payload)


def test_valid_binding_passes() -> None:
    validate_binding(_binding())


def test_version_change_invalidates() -> None:
    with pytest.raises(BindingNotValid):
        validate_binding(_binding(installed_version="0.0.1-never-installed"))


def test_missing_package_invalidates() -> None:
    with pytest.raises(BindingNotValid):
        validate_binding(_binding(package_name="no-such-package-xyz", installed_version="1.0"))


def test_stale_evaluation_invalidates() -> None:
    with pytest.raises(BindingNotValid):
        validate_binding(_binding(evaluation_status="not_run"))


def test_missing_evaluation_ref_invalidates() -> None:
    with pytest.raises(BindingNotValid):
        validate_binding(_binding(evaluation_ref=None))


def test_live_not_run_blocks_production_binding() -> None:
    with pytest.raises(BindingNotValid):
        validate_binding(_binding(live_required=True, live_status="not_run"))


def test_store_loads_and_resolves_by_role(tmp_path: Path) -> None:
    file = tmp_path / "bindings.json"
    file.write_text("[" + _binding().model_dump_json() + "]", encoding="utf-8")
    store = BackendBindingStore.load(file)
    assert store.for_role("auditor") is not None
    assert store.for_role("builder") is None


def test_store_missing_path_is_empty() -> None:
    assert BackendBindingStore.load(None).all() == ()
    assert BackendBindingStore.load("no/such/file.json").all() == ()


def test_store_rejects_duplicate_ids(tmp_path: Path) -> None:
    one = _binding().model_dump_json()
    file = tmp_path / "bindings.json"
    file.write_text(f"[{one}, {one}]", encoding="utf-8")
    with pytest.raises(BindingNotValid):
        BackendBindingStore.load(file)
