"""Tests for D43 runtime lifecycle invariants:
- Engine event loop ownership and advance inside running loops
- Runtime lockfile cleanup on bot completion and error
- Stored runtime_kind field on RunRecord and resume affinity checks
- AsyncOpenAI client aclose lifecycle on backends
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from breakdown.shared.models import Settings
from breakdown.system.runtime.bootstrap import build_runtime
from breakdown.system.runtime.bot import BreakdownBot
from breakdown.system.runtime.demo import OfflineDemoCodingBackend, OfflineDemoRoleBackend
from breakdown.system.runtime.engine import EngineError
from breakdown.system.runtime.live_backend import OpenAICompatibleCodingBackend, OpenAICompatibleRoleBackend

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / "breakdown.yaml"


def _settings(tmp_path: Path) -> Settings:
    target = tmp_path / "target"
    target.mkdir(exist_ok=True)
    return Settings(workflow_path=WORKFLOW, target_repo=target)


def test_lock_released_on_bot_completion(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    state_root = settings.target_repo.resolve() / ".breakdown"

    bot = BreakdownBot.from_settings(settings, offline_demo=True, task_text="research something")
    assert (state_root / "lock").exists()
    bot.close()
    assert not (state_root / "lock").exists()


def test_lock_released_on_bot_context_manager(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    state_root = settings.target_repo.resolve() / ".breakdown"

    with BreakdownBot.from_settings(settings, offline_demo=True, task_text="research something"):
        assert (state_root / "lock").exists()
    assert not (state_root / "lock").exists()


@pytest.mark.asyncio
async def test_lock_released_on_async_context_manager(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    state_root = settings.target_repo.resolve() / ".breakdown"

    async with BreakdownBot.from_settings(settings, offline_demo=True, task_text="research something"):
        assert (state_root / "lock").exists()
    assert not (state_root / "lock").exists()


def test_runtime_kind_stored_in_run_record(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = build_runtime(
        settings,
        role_backend=OfflineDemoRoleBackend("task"),
        coding_backend=OfflineDemoCodingBackend("task"),
        offline_demo=True,
    )
    try:
        record = runtime.engine.start_run("research task", user_identity="test-user")
        assert record.runtime_kind == "offline_demo"

        # Check stored record in RunStore
        loaded = runtime.stores.runs.load(record.run_id)
        assert loaded is not None
        assert loaded[1].runtime_kind == "offline_demo"
    finally:
        runtime.close()


def test_resume_rejects_runtime_kind_mismatch(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = build_runtime(
        settings,
        role_backend=OfflineDemoRoleBackend("task"),
        coding_backend=OfflineDemoCodingBackend("task"),
        offline_demo=True,
        runtime_kind="offline_demo",
    )
    run_id: str
    try:
        record = runtime.engine.start_run("task", user_identity="user")
        run_id = record.run_id
    finally:
        runtime.close()

    # Attempt to advance with mismatched runtime_kind ("live_openai")
    runtime_mismatched = build_runtime(
        settings,
        role_backend=OfflineDemoRoleBackend("task"),
        coding_backend=OfflineDemoCodingBackend("task"),
        offline_demo=True,
        runtime_kind="live_openai",
    )
    try:
        with pytest.raises(EngineError, match="runtime_kind mismatch"):
            runtime_mismatched.engine.advance(run_id)
    finally:
        runtime_mismatched.close()


@pytest.mark.asyncio
async def test_backend_aclose_called_on_live_backend(tmp_path: Path) -> None:
    mock_client = AsyncMock()
    role_backend = OpenAICompatibleRoleBackend(
        client=mock_client,
        model="gpt-4o",
        tool_root=tmp_path,
    )
    coding_backend = OpenAICompatibleCodingBackend(
        client=mock_client,
        model="gpt-4o",
    )

    await role_backend.aclose()
    assert mock_client.close.await_count == 1

    await coding_backend.aclose()
    assert mock_client.close.await_count == 2


@pytest.mark.asyncio
async def test_advance_runs_inside_existing_event_loop(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = build_runtime(
        settings,
        role_backend=OfflineDemoRoleBackend("test request"),
        coding_backend=OfflineDemoCodingBackend("test request"),
        offline_demo=True,
    )
    try:
        record = runtime.engine.start_run("test request", user_identity="async-user")
        advanced = runtime.engine.advance(record.run_id)
        assert advanced is not None
        assert advanced.run_id == record.run_id
    finally:
        runtime.close()
