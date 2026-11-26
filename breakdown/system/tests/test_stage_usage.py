"""Phase 3a — per-stage cost attribution (pattern: per-thread usage metering)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from breakdown.shared.models import CompletionRecord, EventType, StoredValue, TokenUsage

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_t7b():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "t7b_harness_usage", Path(__file__).resolve().parent / "test_engine_budget_recovery.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_happy_path_stage_usage_matches_totals(tmp_path: Path) -> None:
    t7b = _load_t7b()
    h = t7b.Harness(tmp_path)
    record = h.run_to_terminal()
    assert record.terminal_outcome == "success"
    # 4 role activations x 300 tokens (1 call) + coding backend 20 tokens (1 call).
    assert record.tokens_used == 1220
    assert record.tool_calls_used == 5
    totals_tokens = sum(summary.tokens_used for summary in record.stage_usage.values())
    totals_calls = sum(summary.tool_calls_used for summary in record.stage_usage.values())
    assert (totals_tokens, totals_calls) == (record.tokens_used, record.tool_calls_used)
    assert record.stage_usage["research_proposal"].tokens_used == 300
    assert record.stage_usage["build_execution"].tokens_used == 20
    assert record.stage_usage["build_execution"].tool_calls_used == 1
    ref = record.produced_artifacts["completion_record"]
    completion = h.artifacts.get_model(CompletionRecord, ref.artifact_key, ref.revision)
    assert completion.cost_summary is not None
    assert completion.cost_summary.by_stage == record.stage_usage
    assert completion.cost_summary.by_stage["implementation_planning"].tokens_used == 300


def test_failed_attempt_without_reported_usage_attributes_nothing(tmp_path: Path) -> None:
    t7b = _load_t7b()
    h = t7b.Harness(tmp_path, role_fail_times={"create_research_proposal": 1})
    record = h.engine.start_run("request", user_identity="u")
    record = h.engine.advance(record.run_id)  # attempt 1 raises before reporting usage
    assert record.current_stage == "research_approval"
    assert record.stage_attempts["research_proposal"] == 2
    # Only the successful attempt reported usage; accounting never invents cost.
    assert record.stage_usage["research_proposal"].tokens_used == 300
    assert record.stage_usage["research_proposal"].tool_calls_used == 1
    assert record.tokens_used == 300


def test_loopback_accumulates_into_stage(tmp_path: Path) -> None:
    t7b = _load_t7b()
    h = t7b.Harness(tmp_path, coding_outcomes=("blocked", "complete"))
    record = h.engine.start_run("request", user_identity="u")
    run_id = record.run_id
    h.engine.advance(run_id)
    h.engine.record_decision(run_id, "approve", user_identity="u")
    h.engine.advance(run_id)
    h.engine.record_decision(run_id, "approve", user_identity="u")
    h.engine.advance(run_id)  # build #1 blocked -> loopback -> replan -> plan_approval
    h.engine.record_decision(run_id, "approve", user_identity="u")
    record = h.engine.advance(run_id)
    assert record.terminal_outcome == "success"
    assert record.stage_usage["build_execution"].tokens_used == 40  # two builds x 20
    assert record.stage_usage["build_execution"].tool_calls_used == 2
    assert record.stage_usage["implementation_planning"].tokens_used == 600  # planned twice
    totals = sum(summary.tokens_used for summary in record.stage_usage.values())
    assert totals == record.tokens_used


def test_budget_record_contains_stage_usage_snapshot(tmp_path: Path) -> None:
    t7b = _load_t7b()
    h = t7b.Harness(tmp_path, usage=TokenUsage(input_tokens=30_000, output_tokens=15_000, tool_calls=1))
    record = h.run_to_terminal()  # per-stage cap (40k) trips on the first activation
    assert record.reason == "budget_exhausted"
    ref = record.produced_artifacts["budget_exhausted_record"]
    value = h.artifacts.get_model(StoredValue, ref.artifact_key, ref.revision).value
    assert value["stage_usage"] == {"research_proposal": {"tokens_used": 45_000, "tool_calls_used": 1}}
    assert value["tokens_used"] == 45_000


def test_stage_completed_events_carry_usage(tmp_path: Path) -> None:
    t7b = _load_t7b()
    h = t7b.Harness(tmp_path)
    record = h.run_to_terminal()
    completed = [event for event in h.events.load(record.run_id) if event.event_type is EventType.STAGE_COMPLETED]
    assert len(completed) == 5
    by_stage = {event.stage_id: event.payload for event in completed}
    assert by_stage["research_proposal"] == {"tokens": 300, "tool_calls": 1}
    assert by_stage["build_execution"] == {"tokens": 20, "tool_calls": 1}


def test_report_renders_stage_cost_table(tmp_path: Path) -> None:
    from breakdown.system.runtime.reports import render_run_report

    t7b = _load_t7b()
    h = t7b.Harness(tmp_path)
    record = h.run_to_terminal()
    text = render_run_report(record, events=h.events.load(record.run_id))
    assert "## Stage cost" in text
    assert "- build_execution: 20 tokens, 1 tool calls" in text
    assert "- research_proposal: 300 tokens, 1 tool calls" in text
    cost_section = text.split("## Stage cost", 1)[1]
    assert cost_section.index("build_execution") < cost_section.index("research_proposal")
