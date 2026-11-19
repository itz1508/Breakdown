"""Tests for BreakdownBot independent bot runtime and CLI (D40)."""

from __future__ import annotations

from pathlib import Path

import pytest

from breakdown.bot import BreakdownBot
from breakdown.models import Settings


@pytest.fixture
def test_repo(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    return tmp_path


def test_bot_parse_intent(test_repo: Path) -> None:
    bot = BreakdownBot.from_settings(Settings(target_repo=test_repo), offline_demo=True)

    r1 = bot.parse_intent("go research vector search index")
    assert r1["mode"] == "research"
    assert r1["query"] == "vector search index"

    r2 = bot.parse_intent("research how to configure cache")
    assert r2["mode"] == "research"
    assert r2["query"] == "how to configure cache"

    r3 = bot.parse_intent("go plan migration of database")
    assert r3["mode"] == "plan"
    assert r3["query"] == "migration of database"

    r4 = bot.parse_intent("implement subtract function")
    assert r4["mode"] == "build"
    assert r4["query"] == "subtract function"

    r5 = bot.parse_intent("Add divide function with unit tests")
    assert r5["mode"] == "workflow"
    assert r5["query"] == "Add divide function with unit tests"


def test_bot_run_pause_at_approval(test_repo: Path) -> None:
    settings = Settings(target_repo=test_repo)
    bot = BreakdownBot.from_settings(settings, offline_demo=True)

    result = bot.run("go research subtract function", auto_approve=False)
    assert result.status == "awaiting_decision"
    assert result.pending_approval == "research_approval"
    assert "approve" in result.allowed_actions

    # Verify event trail
    event_types = [e.event_type for e in result.events]
    assert "bot_started" in event_types
    assert "intent_resolved" in event_types
    assert "stage_started" in event_types
    assert "approval_needed" in event_types


def test_bot_run_auto_approve_full_cycle(test_repo: Path) -> None:
    settings = Settings(target_repo=test_repo)
    bot = BreakdownBot.from_settings(settings, offline_demo=True)

    events = list(bot.run_stream("Add subtract to calc.py", auto_approve=True))
    event_types = [e.event_type for e in events]

    assert "bot_started" in event_types
    assert "intent_resolved" in event_types
    assert "approval_needed" in event_types
    assert "decision_recorded" in event_types
    assert "completed" in event_types

    final_event = events[-1]
    assert final_event.event_type == "completed"
    assert final_event.payload.get("terminal_outcome") in ("success", "succeeded")


def test_bot_cli_stream(test_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from breakdown.__main__ import main

    exit_code = main([
        "bot",
        "go research vector search",
        "--target",
        str(test_repo),
        "--offline-demo",
        "--stream",
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[bot_started]" in captured.out
    assert "[intent_resolved]" in captured.out
    assert "[approval_needed]" in captured.out


def test_bot_decide_cancel_transitions_to_terminal(test_repo: Path) -> None:
    from breakdown.models import RunState

    settings = Settings(target_repo=test_repo)
    bot = BreakdownBot.from_settings(settings, offline_demo=True)

    result = bot.run("go research subtract function", auto_approve=False)
    assert result.status == "awaiting_decision"

    record = bot.decide(result.run_id, "cancel", reason="user cancelled via bot")
    assert record.state == RunState.TERMINAL
    assert record.terminal_outcome == "cancelled"


def test_bot_persists_and_retrieves_repo_baseline(test_repo: Path) -> None:
    settings = Settings(target_repo=test_repo)
    bot = BreakdownBot.from_settings(settings, offline_demo=True)

    # Execute run to terminal completion
    result = bot.run("implement subtract in calc.py", auto_approve=True)
    assert result.status == "terminal"

    # Inspect cross-session memory for the repository baseline
    mem_docs = bot.memory.list("baselines/")
    assert len(mem_docs) >= 1
    assert mem_docs[0].path.startswith("baselines/")

    # Retrieve baseline map using bot helper
    repo_id = mem_docs[0].path.removeprefix("baselines/").removesuffix(".json")
    baseline = bot.get_repo_baseline(repo_id)
    assert baseline is not None
    assert len(baseline.entries) >= 1
