"""Runtime sandbox lifecycle and isolated source-effect handling."""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from breakdown.shared.models import SourceCheckpoint, SynchronizationResult
from breakdown.system.safety import (
    ChangedPathReport,
    hash_file,
    is_protected_target,
    MAX_SANDBOX_FILE_BYTES,
    MAX_SANDBOX_FILES,
    resolve_contained,
    SafetyError,
    SANDBOX_MANIFEST,
    SandboxError,
    SKIPPED_DIR_NAMES,
    SynchronizationNotAuthorized,
)

class SandboxManager:
    """Own creation, inspection, export and teardown of run-scoped sandboxes."""

    def __init__(self, *, target_root: Path, state_root: Path) -> None:
        self.target_root = target_root.resolve()
        self.state_root = state_root.resolve()
        self.sandboxes_root = self.state_root / "sandboxes"

    def sandbox_root(self, run_id: str) -> Path:
        if not run_id or run_id.strip() != run_id or run_id.startswith("."):
            raise SafetyError(f"invalid run id for sandbox: {run_id!r}")
        if "/" in run_id or chr(92) in run_id or ".." in PurePosixPath(run_id.replace(chr(92), "/")).parts:
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
        """Detect changes by hashing the sandbox against the captured checkpoint."""
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

    def synchronize(self, result: SynchronizationResult, *, run_id: str) -> tuple[str, ...]:
        """Copy only paths authorized by the separate SafetyBoundary policy."""
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
                continue
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
