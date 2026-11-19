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

from breakdown.approvals import DecisionOutcome
from breakdown.automations import (
    EXHAUSTIVE_TRIGGER_KEYS,
    SlackAction,
    SlackReactionAddedTrigger,
    SlackTrigger,
)
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

    def parse_trigger(self, trigger_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Ingest and validate a trigger payload conforming to Automations trigger oneofs (D42).

        Every trigger must use an exhaustive proto key (e.g. 'slackTrigger', 'slackReactionAdded',
        'cron', 'git'). Rejects invented or paraphrased keys.
        """
        if trigger_key not in EXHAUSTIVE_TRIGGER_KEYS:
            raise ValueError(
                f"Invalid trigger key {trigger_key!r}. Must be one of: {sorted(EXHAUSTIVE_TRIGGER_KEYS)!r}. "
                "Never invent or paraphrase keys (e.g. 'slackReaction', 'slack_reaction')."
            )

        if trigger_key == "slackTrigger":
            channel_id = str(payload.get("channel_id", ""))
            SlackTrigger.validate_channel_id(channel_id)
            text = str(payload.get("text", payload.get("message", ""))).strip()
            # Clean @mention prefix if present (e.g. '<@U12345> go research XYZ')
            clean_text = re.sub(r"^<@[A-Z0-9]+>\s*", "", text)
            intent = self.parse_intent(clean_text)
            return {
                "trigger_key": trigger_key,
                "channel_id": channel_id,
                "raw_text": text,
                "task": clean_text or text,
                "intent": intent,
                "user_id": payload.get("user_id", "slack_user"),
            }

        elif trigger_key == "slackReactionAdded":
            channel_id = str(payload.get("channel_id", ""))
            SlackReactionAddedTrigger.validate_channel_id(channel_id)
            reaction = str(payload.get("reaction", "")).strip()
            # Map standard emoji reactions to approval actions if applicable
            action_map = {
                "white_check_mark": "approve",
                "+1": "approve",
                "heavy_check_mark": "approve",
                "x": "decline",
                "-1": "decline",
            }
            action = action_map.get(reaction.strip(":"), "unknown")
            return {
                "trigger_key": trigger_key,
                "channel_id": channel_id,
                "reaction": reaction,
                "mapped_action": action,
                "item_user": payload.get("item_user"),
                "run_id": payload.get("run_id"),
            }

        elif trigger_key == "slackChannelCreated":
            channel_id = str(payload.get("channel_id", ""))
            channel_name = str(payload.get("channel_name", ""))
            return {
                "trigger_key": trigger_key,
                "channel_id": channel_id,
                "channel_name": channel_name,
            }

        # Generic fallback for cron, git, linear, webhook, etc.
        return {
            "trigger_key": trigger_key,
            "task": str(payload.get("task", payload.get("prompt", ""))),
            "payload": payload,
        }

    def emit_slack_action(
        self,
        channel_id: str,
        message: str,
        *,
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        """Emit a canonical Slack action payload with validated channel ID (D42).

        Channel ID must start with:
        - 'C': public channel
        - 'G': private group / channel
        - 'D': automation owner's direct message (DM)
        """
        action = SlackAction(channel_id=channel_id, message=message, thread_ts=thread_ts)
        return {"slack": action.model_dump(exclude_none=True)}

    def run_trigger_stream(
        self,
        trigger_key: str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        auto_approve: bool = False,
    ) -> Iterator[BotEvent]:
        """Execute a trigger payload yielding streaming BotEvents."""
        parsed = self.parse_trigger(trigger_key, payload)

        # Handle Slack reaction as a decision on an existing run if run_id is supplied
        is_reaction = trigger_key == "slackReactionAdded"
        is_approval = parsed.get("mapped_action") in ("approve", "decline")
        if is_reaction and parsed.get("run_id") and is_approval:
            run_id = parsed["run_id"]
            action = parsed["mapped_action"]
            outcome = self.decide(
                run_id,
                action=action,
                user_identity=f"slack_reaction_{parsed.get('reaction')}",
                reason=f"Slack reaction :{parsed.get('reaction')}: recorded",
            )
            yield BotEvent(
                event_type="decision_recorded",
                run_id=run_id,
                session_id=session_id,
                message=f"Recorded decision {action!r} via Slack reaction :{parsed.get('reaction')}:",
                payload={"action": action, "outcome": outcome.action},
            )
            return

        task = parsed.get("task", "")
        if not task:
            raise ValueError(f"No actionable task could be parsed from trigger {trigger_key!r} payload: {payload!r}")

        user_identity = str(parsed.get("user_id", f"{trigger_key}_trigger"))
        yield from self.run_stream(
            task,
            user_identity=user_identity,
            session_id=session_id,
            auto_approve=auto_approve,
        )

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
    ) -> DecisionOutcome:
        """Record decision on a pending approval."""
        return self.engine.approvals.record_decision(
            run_id,
            action=action,
            user_identity=user_identity,
            reason=reason,
        )
