"""Breakdown Bot: Independent event-driven agent bot runtime (D40).

Learns the hosting and multi-agent patterns from Claude Agent SDK and Managed Agents:
- Task ingestion: accepts natural tasks ("go research ...", "go plan ...", "implement ...")
- Event streaming: yields typed BotEvents (stage transitions, approvals, tool calls, completions)
- Session persistence: preserves runs and cross-session baseline memory
- Interactive decision routing: surfaces approvals and resumes seamlessly
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import AwareDatetime, Field

from breakdown.bootstrap import Runtime, build_runtime
from breakdown.engine import WorkflowEngine
from breakdown.memory import MemoryStore, get_baseline_map
from breakdown.models import (
    BaselineMap,
    RunRecord,
    RunState,
    Settings,
    StrictModel,
)


class BotEvent(StrictModel):
    """Event emitted during Breakdown Bot execution."""

    event_type: Literal[
        "bot_started",
        "intent_resolved",
        "stage_started",
        "stage_completed",
        "approval_needed",
        "decision_recorded",
        "completed",
        "failed",
        "cancelled",
    ]
    run_id: str
    session_id: str | None = None
    stage_id: str | None = None
    message: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class BotRunResult(StrictModel):
    """Terminal or paused outcome of a Breakdown Bot invocation."""

    run_id: str
    session_id: str | None = None
    status: Literal["created", "running", "awaiting_decision", "cancelling", "terminal"]
    current_stage: str | None = None
    pending_approval: str | None = None
    allowed_actions: tuple[str, ...] = ()
    events: tuple[BotEvent, ...] = ()
    report_summary: str = ""


class BreakdownBot:
    """Independent Breakdown Bot runner with event streaming and session management."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.engine: WorkflowEngine = runtime.engine
        self.settings: Settings = runtime.settings
        state_root = (self.settings.target_repo.resolve() / self.settings.state_root).resolve()
        self.memory = MemoryStore(state_root)

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        offline_demo: bool = False,
        task_text: str = "",
        force_unlock: bool = False,
    ) -> BreakdownBot:
        """Construct a BreakdownBot using standard bootstrap wiring."""
        if offline_demo:
            from breakdown.demo import OfflineDemoCodingBackend, OfflineDemoRoleBackend

            runtime = build_runtime(
                settings,
                role_backend=OfflineDemoRoleBackend(task_text),
                coding_backend=OfflineDemoCodingBackend(task_text),
                offline_demo=True,
                force_unlock=force_unlock,
            )
        else:
            from breakdown.bootstrap import build_live_backends

            role_backends, coding_backend = build_live_backends(settings)
            runtime = build_runtime(
                settings,
                role_backends=role_backends,
                coding_backend=coding_backend,
                force_unlock=force_unlock,
            )
        return cls(runtime)

    def parse_intent(self, task: str) -> dict[str, Any]:
        """Classify user task intent (e.g. 'go research', 'go plan', full workflow)."""
        stripped = task.strip()
        lower = stripped.lower()
        if re.match(r"^(?:go\s+)?research\b", lower):
            mode = "research"
            query = re.sub(r"^(?:go\s+)?research\s*:?\s*", "", stripped, flags=re.IGNORECASE)
        elif re.match(r"^(?:go\s+)?plan\b", lower):
            mode = "plan"
            query = re.sub(r"^(?:go\s+)?plan\s*:?\s*", "", stripped, flags=re.IGNORECASE)
        elif re.match(r"^(?:go\s+)?(?:build|execute|implement)\b", lower):
            mode = "build"
            query = re.sub(r"^(?:go\s+)?(?:build|execute|implement)\s*:?\s*", "", stripped, flags=re.IGNORECASE)
        else:
            mode = "workflow"
            query = stripped
        return {"mode": mode, "query": query or stripped}

    def get_repo_baseline(self, repository_identity: str) -> BaselineMap | None:
        """Inspect cached baseline map in cross-session memory store."""
        return get_baseline_map(self.memory, repository_identity)

    def close(self) -> None:
        """Release lockfile and close runtime resources (D43)."""
        self.runtime.close()

    async def aclose(self) -> None:
        """Asynchronously close backend clients and release lockfile (D43)."""
        await self.runtime.aclose()

    def __enter__(self) -> BreakdownBot:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    async def __aenter__(self) -> BreakdownBot:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    def run_stream(
        self,
        task: str,
        *,
        user_identity: str = "user",
        session_id: str | None = None,
        run_id: str | None = None,
        auto_approve: bool = False,
    ) -> Iterator[BotEvent]:
        """Execute task yielding streaming BotEvents."""
        intent = self.parse_intent(task)

        # Start or resume run
        if run_id is None:
            record = self.engine.start_run(task, user_identity=user_identity, session_id=session_id)
            run_id = record.run_id
            yield BotEvent(
                event_type="bot_started",
                run_id=run_id,
                session_id=session_id,
                message=f"Bot started run {run_id}",
                payload={"task": task, "intent": intent},
            )
            yield BotEvent(
                event_type="intent_resolved",
                run_id=run_id,
                session_id=session_id,
                message=f"Task intent resolved to {intent['mode']}",
                payload=intent,
            )
        else:
            record = self.engine._reload(run_id)
            yield BotEvent(
                event_type="bot_started",
                run_id=run_id,
                session_id=session_id,
                message=f"Bot resumed run {run_id}",
                payload={"task": task},
            )

        # Advance loop
        while record.state not in (RunState.TERMINAL,):
            current_stage = record.current_stage or "unknown"
            yield BotEvent(
                event_type="stage_started",
                run_id=run_id,
                session_id=session_id,
                stage_id=current_stage,
                message=f"Advancing stage '{current_stage}'",
            )

            record = self.engine.advance(run_id)

            if record.state is RunState.AWAITING_DECISION:
                stage_id = record.current_stage or "unknown"
                stage_def = self.engine.definition.get_stage(stage_id)
                options = tuple(stage_def.options)

                yield BotEvent(
                    event_type="approval_needed",
                    run_id=run_id,
                    session_id=session_id,
                    stage_id=stage_id,
                    message=f"Approval needed for stage '{stage_id}': actions={options}",
                    payload={"stage_id": stage_id, "allowed_actions": options},
                )

                if auto_approve and "approve" in options:
                    record = self.engine.record_decision(
                        run_id,
                        action="approve",
                        user_identity="bot_auto_approve",
                        reason="Automatic approval granted by BreakdownBot",
                    )
                    yield BotEvent(
                        event_type="decision_recorded",
                        run_id=run_id,
                        session_id=session_id,
                        stage_id=stage_id,
                        message=f"Auto-approved stage '{stage_id}'",
                        payload={"action": "approve"},
                    )
                    continue
                else:
                    # Paused at awaiting decision for user input
                    break

            yield BotEvent(
                event_type="stage_completed",
                run_id=run_id,
                session_id=session_id,
                stage_id=current_stage,
                message=f"Stage '{current_stage}' finished (run state: {record.state.value})",
                payload={"state": record.state.value, "terminal_outcome": record.terminal_outcome},
            )

        # Terminal events
        if record.state is RunState.TERMINAL:
            outcome = record.terminal_outcome or "completed"
            if outcome in ("succeeded", "success"):
                yield BotEvent(
                    event_type="completed",
                    run_id=run_id,
                    session_id=session_id,
                    message=f"Run {run_id} completed successfully",
                    payload={"terminal_outcome": outcome},
                )
            elif outcome == "cancelled":
                yield BotEvent(
                    event_type="cancelled",
                    run_id=run_id,
                    session_id=session_id,
                    message=f"Run {run_id} was cancelled",
                    payload={"terminal_outcome": outcome},
                )
            else:
                yield BotEvent(
                    event_type="failed",
                    run_id=run_id,
                    session_id=session_id,
                    message=f"Run {run_id} terminated with outcome: {outcome}",
                    payload={"terminal_outcome": outcome, "reason": record.reason},
                )

    async def astream(
        self,
        task: str,
        *,
        user_identity: str = "user",
        session_id: str | None = None,
        run_id: str | None = None,
        auto_approve: bool = False,
    ) -> AsyncIterator[BotEvent]:
        """Asynchronously stream BotEvents."""
        for event in self.run_stream(
            task,
            user_identity=user_identity,
            session_id=session_id,
            run_id=run_id,
            auto_approve=auto_approve,
        ):
            yield event

    def run(
        self,
        task: str,
        *,
        user_identity: str = "user",
        session_id: str | None = None,
        run_id: str | None = None,
        auto_approve: bool = False,
    ) -> BotRunResult:
        """Run task and collect all events into a final BotRunResult."""
        events: list[BotEvent] = []
        for event in self.run_stream(
            task,
            user_identity=user_identity,
            session_id=session_id,
            run_id=run_id,
            auto_approve=auto_approve,
        ):
            events.append(event)

        active_run_id = events[0].run_id if events else (run_id or "unknown")
        record: RunRecord = self.engine._reload(active_run_id)

        pending_stage = None
        allowed_actions: tuple[str, ...] = ()
        if record.state is RunState.AWAITING_DECISION and record.current_stage:
            stage_def = self.engine.definition.get_stage(record.current_stage)
            pending_stage = record.current_stage
            allowed_actions = tuple(stage_def.options)

        summary = f"Run {active_run_id} state={record.state.value} outcome={record.terminal_outcome or 'none'}"
        return BotRunResult(
            run_id=active_run_id,
            session_id=session_id,
            status=record.state.value,
            current_stage=record.current_stage,
            pending_approval=pending_stage,
            allowed_actions=allowed_actions,
            events=tuple(events),
            report_summary=summary,
        )

    def decide(
        self,
        run_id: str,
        action: str,
        *,
        user_identity: str = "user",
        reason: str = "",
    ) -> RunRecord:
        """Record decision on a pending approval and update workflow lifecycle."""
        return self.engine.record_decision(
            run_id,
            action=action,
            user_identity=user_identity,
            reason=reason,
        )
