"""P2-T4 — safety boundary: sandbox, changed-path detection, synchronization.

These rows score the three builder blocking zeros that were not_run in
Phase 1: unexpected paths, authoritative-repo writes, and unauthorized
synchronization.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from breakdown.checkpoint import capture_source_checkpoint
from breakdown.models import SynchronizationResult
from breakdown.safety import (
    SANDBOX_MANIFEST,
    ChangedPathReport,
    ContainmentError,
    SafetyBoundary,
    SafetyError,
    SandboxError,
    SynchronizationNotAuthorized,
    is_protected_target,
    resolve_contained,
)


@pytest.fixture
def target(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    return repo


@pytest.fixture
def boundary(tmp_path: Path, target: Path) -> SafetyBoundary:
    return SafetyBoundary(target_root=target, state_root=tmp_path / "state")


def _all_valid(report: ChangedPathReport) -> dict[str, object]:
    return {
        "report": report,
        "approved_paths": tuple(report.all),
        "task_results_valid": True,
        "integration_valid": True,
        "bindings_current": True,
        "preconditions_current": True,
    }


def test_sandbox_copies_exactly_checkpoint_listed_files(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    root = boundary.create_sandbox("run-1", checkpoint)
    copied = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert copied == set(checkpoint.file_hashes)


def test_sandbox_double_create_rejected(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    boundary.create_sandbox("run-1", checkpoint)
    with pytest.raises(SandboxError):
        boundary.create_sandbox("run-1", checkpoint)


def test_sandbox_run_id_containment(boundary: SafetyBoundary) -> None:
    for bad in ("../escape", "..", "a/b", ".hidden", " padded"):
        with pytest.raises(SafetyError):
            boundary.sandbox_root(bad)


def test_detect_no_changes(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    boundary.create_sandbox("run-1", checkpoint)
    report = boundary.detect_changed_paths("run-1", checkpoint)
    assert report.all == frozenset()


def test_detect_added_modified_deleted(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    root = boundary.create_sandbox("run-1", checkpoint)
    (root / "src" / "new.py").write_text("x = 1\n", encoding="utf-8")
    (root / "src" / "calc.py").write_text("changed\n", encoding="utf-8")
    (root / "README.md").unlink()
    report = boundary.detect_changed_paths("run-1", checkpoint)
    assert report.added == frozenset({"src/new.py"})
    assert report.modified == frozenset({"src/calc.py"})
    assert report.deleted == frozenset({"README.md"})


def test_detect_without_sandbox_raises(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    with pytest.raises(SandboxError):
        boundary.detect_changed_paths("ghost", checkpoint)


def test_authorize_blocks_unexpected_paths(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    root = boundary.create_sandbox("run-1", checkpoint)
    (root / "src" / "sneaky.py").write_text("x\n", encoding="utf-8")
    report = boundary.detect_changed_paths("run-1", checkpoint)
    result = boundary.authorize_synchronization(
        report=report,
        approved_paths=("src/calc.py",),
        task_results_valid=True,
        integration_valid=True,
        bindings_current=True,
        preconditions_current=True,
    )
    assert result.authorized is False
    assert "unexpected changed paths" in (result.blocked_reason or "")


@pytest.mark.parametrize(
    "flag",
    ["task_results_valid", "integration_valid", "bindings_current", "preconditions_current"],
)
def test_authorize_blocks_when_any_requirement_false(boundary: SafetyBoundary, target: Path, flag: str) -> None:
    checkpoint = capture_source_checkpoint(target)
    root = boundary.create_sandbox("run-1", checkpoint)
    (root / "src" / "calc.py").write_text("changed\n", encoding="utf-8")
    report = boundary.detect_changed_paths("run-1", checkpoint)
    kwargs = _all_valid(report)
    kwargs[flag] = False
    result = boundary.authorize_synchronization(**kwargs)  # type: ignore[arg-type]
    assert result.authorized is False
    assert result.blocked_reason


def test_authorize_blocks_protected_paths(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    root = boundary.create_sandbox("run-1", checkpoint)
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    report = boundary.detect_changed_paths("run-1", checkpoint)
    assert ".env" in report.added
    result = boundary.authorize_synchronization(**_all_valid(report))  # type: ignore[arg-type]
    assert result.authorized is False
    assert "protected" in (result.blocked_reason or "")


def test_target_untouched_until_authorized_sync(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    root = boundary.create_sandbox("run-1", checkpoint)
    before = (target / "src" / "calc.py").read_text(encoding="utf-8")
    (root / "src" / "calc.py").write_text("def add(a, b):\n    return a * b\n", encoding="utf-8")
    boundary.detect_changed_paths("run-1", checkpoint)
    assert (target / "src" / "calc.py").read_text(encoding="utf-8") == before


def test_unauthorized_synchronize_raises(boundary: SafetyBoundary) -> None:
    blocked = SynchronizationResult(authorized=False, blocked_reason="unexpected paths")
    with pytest.raises(SynchronizationNotAuthorized):
        boundary.synchronize(blocked, run_id="run-1")


def test_synchronize_copies_only_approved_changed_paths(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    root = boundary.create_sandbox("run-1", checkpoint)
    (root / "src" / "calc.py").write_text("def add(a, b):\n    return a * b\n", encoding="utf-8")
    (root / "README.md").unlink()
    report = boundary.detect_changed_paths("run-1", checkpoint)
    result = boundary.authorize_synchronization(**_all_valid(report))  # type: ignore[arg-type]
    assert result.authorized is True
    copied = boundary.synchronize(result, run_id="run-1")
    assert set(copied) == {"src/calc.py", "README.md"}
    assert "a * b" in (target / "src" / "calc.py").read_text(encoding="utf-8")
    assert not (target / "README.md").exists()


def test_synchronize_manifest_excluded_and_teardown(boundary: SafetyBoundary, target: Path) -> None:
    checkpoint = capture_source_checkpoint(target)
    root = boundary.create_sandbox("run-1", checkpoint)
    (root / SANDBOX_MANIFEST).write_text("{}", encoding="utf-8")
    report = boundary.detect_changed_paths("run-1", checkpoint)
    assert SANDBOX_MANIFEST not in report.all
    boundary.teardown_sandbox("run-1")
    assert not root.exists()


def test_resolve_contained_and_protection_helpers(tmp_path: Path) -> None:
    with pytest.raises(ContainmentError):
        resolve_contained(tmp_path, "../outside")
    assert is_protected_target(".env")
    assert is_protected_target("agents/skills/x/SKILL.md")
    assert not is_protected_target("src/calc.py")
