"""P2-T3 — source checkpoint capture and freshness (tmp git repos)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from breakdown.checkpoint import CheckpointError, capture_source_checkpoint, checkpoint_is_fresh


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "base")
    return tmp_path


def test_git_checkpoint_identity_and_hashes(git_repo: Path) -> None:
    checkpoint = capture_source_checkpoint(git_repo)
    assert checkpoint.commit_sha is not None
    assert len(checkpoint.commit_sha) == 40
    assert "src/calc.py" in checkpoint.file_hashes
    assert "README.md" in checkpoint.file_hashes
    assert dict(checkpoint.untracked_file_hashes) == {}


def test_git_untracked_files_tracked_separately(git_repo: Path) -> None:
    (git_repo / "new_file.txt").write_text("untracked\n", encoding="utf-8")
    checkpoint = capture_source_checkpoint(git_repo)
    assert "new_file.txt" in checkpoint.untracked_file_hashes
    assert "new_file.txt" not in checkpoint.file_hashes


def test_non_git_fallback_walks_tree(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("b\n", encoding="utf-8")
    checkpoint = capture_source_checkpoint(tmp_path)
    assert checkpoint.commit_sha is None
    assert checkpoint.repository_identity == str(tmp_path.resolve())
    assert set(checkpoint.file_hashes) == {"a.py", "sub/b.py"}


def test_runtime_state_and_venv_excluded(tmp_path: Path) -> None:
    (tmp_path / ".breakdown").mkdir()
    (tmp_path / ".breakdown" / "runs.db").write_text("x", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("x", encoding="utf-8")
    (tmp_path / "keep.py").write_text("k\n", encoding="utf-8")
    checkpoint = capture_source_checkpoint(tmp_path)
    assert set(checkpoint.file_hashes) == {"keep.py"}


def test_freshness_detects_drift(git_repo: Path) -> None:
    checkpoint = capture_source_checkpoint(git_repo)
    assert checkpoint_is_fresh(checkpoint, git_repo)
    (git_repo / "src" / "calc.py").write_text("x = 2\n", encoding="utf-8")
    assert not checkpoint_is_fresh(checkpoint, git_repo)


def test_missing_root_rejected(tmp_path: Path) -> None:
    with pytest.raises(CheckpointError):
        capture_source_checkpoint(tmp_path / "ghost")
