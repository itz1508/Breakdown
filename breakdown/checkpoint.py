"""Source checkpoint: deterministic repository identity measurement.

A runtime deterministic operation — never model-invoked and never exposed
as a tool. Git repositories are identified by origin URL (fallback:
absolute path) plus HEAD commit; file contents are hashed in sorted path
order. Non-git targets fall back to path identity plus a full walk
(Decision D14). The checkpoint feeds source_checkpoint_hash, preflight
freshness, and sandbox construction.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from breakdown.models import SourceCheckpoint
from breakdown.tools import SKIPPED_DIR_NAMES

_SKIP_DIRS = frozenset(SKIPPED_DIR_NAMES | {".breakdown"})


class CheckpointError(RuntimeError):
    pass


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _skipped(relative: str) -> bool:
    return any(part in _SKIP_DIRS for part in Path(relative).parts)


def capture_source_checkpoint(root: Path) -> SourceCheckpoint:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise CheckpointError(f"checkpoint root is not a directory: {root}")
    is_git = (resolved / ".git").exists()
    repository_identity = str(resolved)
    commit_sha: str | None = None
    if is_git:
        repository_identity = _git(resolved, "remote", "get-url", "origin") or str(resolved)
        commit_sha = _git(resolved, "rev-parse", "HEAD")  # None in an empty repo

    file_hashes: dict[str, str] = {}
    untracked_hashes: dict[str, str] = {}
    if is_git and commit_sha is not None:
        tracked = _git(resolved, "ls-files") or ""
        for relative in tracked.splitlines():
            relative = relative.strip()
            if not relative or _skipped(relative):
                continue
            path = resolved / relative
            if path.is_file():
                file_hashes[relative.replace("\\", "/")] = _hash_file(path)
        untracked = _git(resolved, "ls-files", "--others", "--exclude-standard") or ""
        for relative in untracked.splitlines():
            relative = relative.strip()
            if not relative or _skipped(relative):
                continue
            path = resolved / relative
            if path.is_file():
                untracked_hashes[relative.replace("\\", "/")] = _hash_file(path)
    else:
        for path in sorted(resolved.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(resolved).as_posix()
            if _skipped(relative):
                continue
            file_hashes[relative] = _hash_file(path)

    return SourceCheckpoint(
        repository_identity=repository_identity,
        commit_sha=commit_sha,
        file_hashes=file_hashes,
        untracked_file_hashes=untracked_hashes,
        captured_at=datetime.now(UTC),
    )


def checkpoint_is_fresh(recorded: SourceCheckpoint, root: Path) -> bool:
    """Preflight freshness: content hashes and commit still match.

    ``captured_at`` and identity strings are deliberately not compared —
    a re-capture always differs in timestamp.
    """
    current = capture_source_checkpoint(root)
    return (
        dict(current.file_hashes) == dict(recorded.file_hashes)
        and dict(current.untracked_file_hashes) == dict(recorded.untracked_file_hashes)
        and current.commit_sha == recorded.commit_sha
    )
