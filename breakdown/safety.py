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
import os
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from breakdown.models import PROTECTED_PATHS, SourceCheckpoint, SynchronizationResult

MAX_SANDBOX_FILES = 50_000
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
    def __init__(self, *, target_root: Path, state_root: Path) -> None:
        self.target_root = target_root.resolve()
        self.state_root = state_root.resolve()
        self.sandboxes_root = self.state_root / "sandboxes"

    def sandbox_root(self, run_id: str) -> Path:
        if not run_id or run_id.strip() != run_id or run_id.startswith("."):
            raise SafetyError(f"invalid run id for sandbox: {run_id!r}")
        if "/" in run_id or "\\" in run_id or ".." in PurePosixPath(run_id.replace("\\", "/")).parts:
            raise SafetyError(f"invalid run id for sandbox: {run_id!r}")
        return self.sandboxes_root / run_id

    def create_sandbox(self, run_id: str, checkpoint: SourceCheckpoint) -> Path:
        root = self.sandbox_root(run_id)
        if root.exists():
            raise SandboxError(f"sandbox already exists for run {run_id}")
        listed = sorted(set(checkpoint.file_hashes) | set(checkpoint.untracked_file_hashes))
        if len(listed) > MAX_SANDBOX_FILES:
            raise SandboxError(f"checkpoint lists {len(listed)} files; cap is {MAX_SANDBOX_FILES}")
        root.mkdir(parents=True)
        for relative in listed:
            source = resolve_contained(self.target_root, relative)
            if not source.is_file():
                shutil.rmtree(root, ignore_errors=True)
                raise SandboxError(f"checkpoint-listed file is missing: {relative}")
            if source.stat().st_size > MAX_SANDBOX_FILE_BYTES:
                shutil.rmtree(root, ignore_errors=True)
                raise SandboxError(f"checkpoint-listed file exceeds the size cap: {relative}")
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        return root

    def detect_changed_paths(self, run_id: str, checkpoint: SourceCheckpoint) -> ChangedPathReport:
        """Independent changed-path detection: hash diff against the approved
        checkpoint. Never consumes builder-reported paths."""
        root = self.sandbox_root(run_id)
        if not root.is_dir():
            raise SandboxError(f"no sandbox for run {run_id}")
        baseline = dict(checkpoint.file_hashes)
        baseline.update(checkpoint.untracked_file_hashes)
        added: set[str] = set()
        modified: set[str] = set()
        seen: set[str] = set()
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative == SANDBOX_MANIFEST or any(part in SKIPPED_DIR_NAMES for part in Path(relative).parts):
                continue
            seen.add(relative)
            if relative not in baseline:
                added.add(relative)
            elif baseline[relative] != hash_file(path):
                modified.add(relative)
        deleted = set(baseline) - seen
        return ChangedPathReport(added=frozenset(added), modified=frozenset(modified), deleted=frozenset(deleted))

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
        """Authorized-only, atomic copy-back of approved changed paths."""
        if not result.authorized:
            raise SynchronizationNotAuthorized(
                f"synchronization is not authorized: {result.blocked_reason or 'unknown reason'}"
            )
        root = self.sandbox_root(run_id)
        if not root.is_dir():
            raise SandboxError(f"no sandbox for run {run_id}")
        copied: list[str] = []
        for relative in sorted(result.copied_paths):
            if is_protected_target(relative):
                raise SynchronizationNotAuthorized(f"protected path cannot be synchronized: {relative}")
            source = resolve_contained(root, relative)
            destination = resolve_contained(self.target_root, relative)
            if source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(destination.name + ".breakdown-tmp")
                shutil.copyfile(source, temporary)
                os.replace(temporary, destination)
            elif destination.exists():
                destination.unlink()
            else:
                continue  # deleted in sandbox and absent in target: nothing to do
            copied.append(relative)
        self._reconcile(copied, root)
        return tuple(copied)

    def _reconcile(self, copied: Sequence[str], root: Path) -> None:
        for relative in copied:
            source = root / relative
            destination = self.target_root / relative
            if source.is_file():
                if not destination.is_file() or hash_file(destination) != hash_file(source):
                    raise SafetyError(f"reconciliation failed for {relative}")
            elif destination.exists():
                raise SafetyError(f"reconciliation failed: {relative} still exists in the target")

    def teardown_sandbox(self, run_id: str) -> None:
        root = self.sandbox_root(run_id)
        if root.exists():
            shutil.rmtree(root)
