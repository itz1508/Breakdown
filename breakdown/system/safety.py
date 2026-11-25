"""Safety boundary: sandbox lifecycle, path containment, synchronization.

The deterministic safety authority of the workflow (Phase 2, P2-T4).
Owns:

- read-containment helpers shared with canonical tools (tools.py imports
  from here; this module never imports tools),
- sandbox creation from a source checkpoint (checkpoint-listed files only),
- independent changed-path detection (hash diff; never consumes
  builder-reported paths),
- synchronization authorization implementing the yaml
  ``build_execution.synchronization.requires`` block, and
- authorized, atomic, reconciled copy-back of approved paths only.

Builder work never touches the authoritative repository until runtime
authorizes synchronization here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from breakdown.shared.models import PROTECTED_PATHS, SourceCheckpoint, SynchronizationResult

MAX_SANDBOX_FILES = 50_000

# Implemented authorization checks — mirrors breakdown.yaml
# build_execution.authorization_checks (drift is pinned by
# contracts.validate_definition_consistency / `--check`).
AUTHORIZATION_CHECKS: tuple[str, ...] = (
    "approval_action_is_approve",
    "approval_hash_matches",
    "frozen_plan_hash_matches",
    "source_checkpoint_matches",
    "preflight_result.criterion_result == valid",
    "task_targets_match_approved_plan",
)

# Implemented synchronization requirements — mirrors breakdown.yaml
# build_execution.synchronization.requires (pinned the same way).
SYNCHRONIZATION_REQUIRES: tuple[str, ...] = (
    "task_results_valid",
    "integration_validation_valid",
    "no_unexpected_paths",
    "approval_bindings_current",
    "source_preconditions_current",
)
MAX_SANDBOX_FILE_BYTES = 10_000_000
SANDBOX_MANIFEST = ".breakdown-sandbox-manifest.json"

SKIPPED_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".breakdown",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)


class SafetyError(RuntimeError):
    pass


class ContainmentError(SafetyError):
    """A path escapes containment or names a denied resource."""


class SandboxError(SafetyError):
    pass


class SynchronizationNotAuthorized(SafetyError):
    pass


def is_denied_read_name(name: str) -> bool:
    return name == ".env" or name.startswith(".env.")


def is_protected_target(relative: str) -> bool:
    normalized = PurePosixPath(relative.replace("\\", "/")).as_posix()
    head = normalized.split("/", 1)[0]
    return normalized in PROTECTED_PATHS or head in PROTECTED_PATHS


def resolve_contained(root: Path, relative: str) -> Path:
    """Resolve ``relative`` strictly inside ``root`` or raise ContainmentError."""
    if not relative or relative.strip() != relative:
        raise ContainmentError("path must be a non-empty, unpadded relative path")
    candidate = root / relative.replace("\\", "/")
    resolved_root = root.resolve()
    try:
        resolved = candidate.resolve()
    except OSError as exc:  # pragma: no cover - platform path errors
        raise ContainmentError(f"path cannot be resolved: {relative}") from exc
    if not resolved.is_relative_to(resolved_root):
        raise ContainmentError(f"path escapes containment: {relative}")
    return resolved


def hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass(frozen=True, slots=True)
class ChangedPathReport:
    added: frozenset[str]
    modified: frozenset[str]
    deleted: frozenset[str]

    @property
    def all(self) -> frozenset[str]:
        return self.added | self.modified | self.deleted


class SafetyBoundary:
    """Central safety policy; delegates sandbox mechanics to Runtime."""

    def __init__(self, *, target_root: Path, state_root: Path) -> None:
        self.target_root = target_root.resolve()
        self.state_root = state_root.resolve()
        from breakdown.system.runtime.sandbox import SandboxManager

        self._sandbox = SandboxManager(target_root=self.target_root, state_root=self.state_root)

    def sandbox_root(self, run_id: str) -> Path:
        return self._sandbox.sandbox_root(run_id)

    def create_sandbox(self, run_id: str, checkpoint: SourceCheckpoint) -> Path:
        return self._sandbox.create_sandbox(run_id, checkpoint)

    def detect_changed_paths(self, run_id: str, checkpoint: SourceCheckpoint) -> ChangedPathReport:
        return self._sandbox.detect_changed_paths(run_id, checkpoint)

    def authorize_synchronization(
        self,
        *,
        report: ChangedPathReport,
        approved_paths: Iterable[str],
        task_results_valid: bool,
        integration_valid: bool,
        bindings_current: bool,
        preconditions_current: bool,
    ) -> SynchronizationResult:
        """Implements build_execution.synchronization.requires plus approved-path
        containment. Any violation blocks all synchronization."""
        reasons: list[str] = []
        approved = {PurePosixPath(p.replace("\\", "/")).as_posix() for p in approved_paths}
        unexpected = sorted(report.all - approved)
        protected = sorted(path for path in report.all if is_protected_target(path))
        if unexpected:
            reasons.append(f"unexpected changed paths: {unexpected}")
        if protected:
            reasons.append(f"protected paths cannot be synchronized: {protected}")
        if not task_results_valid:
            reasons.append("task results are not all valid")
        if not integration_valid:
            reasons.append("integration validation is not valid")
        if not bindings_current:
            reasons.append("approval bindings are not current")
        if not preconditions_current:
            reasons.append("source preconditions are not current")
        if reasons:
            return SynchronizationResult(authorized=False, blocked_reason="; ".join(reasons))
        return SynchronizationResult(authorized=True, copied_paths=tuple(sorted(report.all)))


    def synchronize(self, result: SynchronizationResult, *, run_id: str) -> tuple[str, ...]:
        return self._sandbox.synchronize(result, run_id=run_id)

    def teardown_sandbox(self, run_id: str) -> None:
        self._sandbox.teardown_sandbox(run_id)
