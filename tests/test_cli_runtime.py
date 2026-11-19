"""P2-T9 — bootstrap.build_runtime, lockfile guard, and the CLI surface."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from breakdown.bindings import BindingNotValid
from breakdown.bootstrap import BootstrapError, LockfileGuard, build_runtime
from breakdown.demo import OfflineDemoCodingBackend, OfflineDemoRoleBackend
from breakdown.models import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / "breakdown.yaml"


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    target = tmp_path / "target"
    target.mkdir(exist_ok=True)
    base: dict[str, object] = {"workflow_path": WORKFLOW, "target_repo": target}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _demo_backends() -> dict[str, object]:
    return {
        "role_backend": OfflineDemoRoleBackend("demo request"),
        "coding_backend": OfflineDemoCodingBackend("demo request"),
    }


def test_build_runtime_creates_state_and_lockfile(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = build_runtime(settings, offline_demo=True, **_demo_backends())  # type: ignore[arg-type]
    state_root = settings.target_repo.resolve() / ".breakdown"
    assert state_root.is_dir()
    assert (state_root / "lock").exists()
    # A second construction against the same state must fail while locked.
    with pytest.raises(BootstrapError, match="locked"):
        build_runtime(settings, offline_demo=True, **_demo_backends())  # type: ignore[arg-type]
    runtime.lock.release()
    assert not (state_root / "lock").exists()
    runtime2 = build_runtime(settings, offline_demo=True, **_demo_backends())  # type: ignore[arg-type]
    runtime2.lock.release()


def test_lockfile_guard_force_takes_over_stale_lock(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    state_root = settings.target_repo.resolve() / ".breakdown"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "lock").write_text("pid=999999", encoding="utf-8")
    with pytest.raises(BootstrapError, match="999999"):
        build_runtime(settings, offline_demo=True, **_demo_backends())  # type: ignore[arg-type]
    runtime = build_runtime(settings, offline_demo=True, force_unlock=True, **_demo_backends())  # type: ignore[arg-type]
    assert f"pid={__import__('os').getpid()}" in (state_root / "lock").read_text(encoding="utf-8")
    runtime.lock.release()


def test_lockfile_release_ignores_foreign_lock(tmp_path: Path) -> None:
    guard = LockfileGuard(tmp_path)
    guard.path.write_text("pid=424242", encoding="utf-8")
    guard.release()  # must not delete a lock this process does not own
    assert guard.path.exists()


def test_build_runtime_validates_bindings_unless_offline_demo(tmp_path: Path) -> None:
    bindings_path = tmp_path / "bindings.json"
    bindings_path.write_text(
        json.dumps(
            [
                {
                    "binding_id": "binding-bad",
                    "role": "auditor",
                    "implementation": "fake",
                    "package_name": "no-such-package-xyz",
                    "installed_version": "1.0",
                    "evaluation_ref": {"artifact_key": "backend_evaluation", "digest": "a" * 64},
                    "evaluation_status": "completed",
                    "permitted_operations": ["create_research_proposal"],
                    "required_capabilities": ["structured_output"],
                    "live_required": False,
                    "binding_revision": 1,
                    "approved_at": "2026-11-17T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )
    settings = _settings(tmp_path, backend_bindings_path=bindings_path)
    with pytest.raises(BindingNotValid):
        build_runtime(settings, **_demo_backends())  # type: ignore[arg-type]
    runtime = build_runtime(settings, offline_demo=True, **_demo_backends())  # type: ignore[arg-type]
    assert len(runtime.bindings.all()) == 1
    runtime.lock.release()


def _cli(tmp_path: Path, *args: str, target: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "breakdown", *args]
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)


def test_cli_check_still_green() -> None:
    result = _cli(Path("."), "--check", "--workflow", str(WORKFLOW))
    assert result.returncode == 0
    assert "8 aligned" in result.stdout


def test_cli_requires_offline_demo_flag(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    result = _cli(tmp_path, "run", "demo", "--workflow", str(WORKFLOW), "--target", str(target))
    assert result.returncode == 1
    assert "--offline-demo" in result.stdout


def _run_id(stdout: str) -> str:
    match = re.search(r"run: (\S+)", stdout)
    assert match, f"no run id in output:\n{stdout}"
    return match.group(1)


def test_cli_offline_demo_full_run(tmp_path: Path) -> None:
    """Subprocess e2e: run -> decide -> resume across separate CLI processes."""
    target = tmp_path / "target"
    target.mkdir()
    common = ("--workflow", str(WORKFLOW), "--target", str(target), "--offline-demo")

    r1 = _cli(tmp_path, "run", "Create the demo change record", *common)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert "state: awaiting_decision" in r1.stdout
    assert "stage: research_approval" in r1.stdout
    run_id = _run_id(r1.stdout)

    r2 = _cli(tmp_path, "decide", run_id, "approve", *common)
    assert r2.returncode == 0, r2.stdout + r2.stderr

    r3 = _cli(tmp_path, "resume", run_id, *common)
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert "stage: plan_approval" in r3.stdout

    r4 = _cli(tmp_path, "decide", run_id, "approve", *common)
    assert r4.returncode == 0, r4.stdout + r4.stderr

    r5 = _cli(tmp_path, "resume", run_id, *common)
    assert r5.returncode == 0, r5.stdout + r5.stderr
    assert "outcome: success" in r5.stdout

    demo_file = target / "DEMO_CHANGE.md"
    assert demo_file.exists()
    assert "Create the demo change record" in demo_file.read_text(encoding="utf-8")

    r6 = _cli(tmp_path, "status", run_id, "--workflow", str(WORKFLOW), "--target", str(target))
    assert r6.returncode == 0, r6.stdout + r6.stderr
    assert run_id in r6.stdout
    assert "completion_record" in r6.stdout
    assert "terminal outcome: success" in r6.stdout


def test_cli_cancel_and_status(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    common = ("--workflow", str(WORKFLOW), "--target", str(target), "--offline-demo")
    r1 = _cli(tmp_path, "run", "demo request", *common)
    run_id = _run_id(r1.stdout)
    r2 = _cli(tmp_path, "cancel", run_id, "--reason", "changed my mind", *common)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "outcome: cancelled" in r2.stdout
    r3 = _cli(tmp_path, "status", run_id, "--workflow", str(WORKFLOW), "--target", str(target))
    assert "terminal outcome: cancelled" in r3.stdout


def test_cli_error_paths(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    common = ("--workflow", str(WORKFLOW), "--target", str(target), "--offline-demo")
    # Unknown run id -> clean error, nonzero exit.
    r1 = _cli(tmp_path, "decide", "run-ghost", "approve", *common)
    assert r1.returncode == 1
    assert "error:" in r1.stdout
    # Status before any state exists.
    r2 = _cli(tmp_path, "status", "run-ghost", "--workflow", str(WORKFLOW), "--target", str(target))
    assert r2.returncode == 1


def test_cli_lock_blocks_concurrent_process(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    state_root = target / ".breakdown"
    state_root.mkdir()
    (state_root / "lock").write_text("pid=999999", encoding="utf-8")
    common = ("--workflow", str(WORKFLOW), "--target", str(target), "--offline-demo")
    r1 = _cli(tmp_path, "run", "demo", *common)
    assert r1.returncode == 1
    assert "locked" in r1.stdout
    r2 = _cli(tmp_path, "run", "demo", *common, "--force-unlock")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "state: awaiting_decision" in r2.stdout
