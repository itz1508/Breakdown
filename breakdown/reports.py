"""Markdown projections of durable run state.

Reports are projections, never sources of truth: every artifact is cited by
``key@revision`` and its CAS digest so a reader can verify each claim against
the stores. Reports embed no artifact payloads and no wall-clock time —
rendering the same stored state twice yields identical Markdown.
"""

from __future__ import annotations

from collections.abc import Sequence

from breakdown.models import ArtifactRef, RunRecord, WorkflowEvent


def cite(ref: ArtifactRef) -> str:
    """Digest citation for one stored artifact (verifiable against the CAS)."""
    return f"{ref.artifact_key}@{ref.revision} digest:{ref.digest}"


def render_run_report(record: RunRecord, events: Sequence[WorkflowEvent] = ()) -> str:
    """Deterministic Markdown projection of one run record."""
    lines = [
        f"# Run report: {record.run_id}",
        "",
        f"- state: {record.state.value}",
        f"- current stage: {record.current_stage or '-'}",
    ]
    if record.terminal_outcome:
        lines.append(f"- terminal outcome: {record.terminal_outcome}")
    if record.reason:
        lines.append(f"- reason: {record.reason}")
    lines += [
        f"- session: {record.session_id}",
        f"- definition: version {record.definition_version} digest:{record.definition_digest}",
        f"- cost: {record.tokens_used} tokens, {record.tool_calls_used} tool calls",
        "",
        "## Produced artifacts",
        "",
    ]
    if record.produced_artifacts:
        for key in sorted(record.produced_artifacts):
            lines.append(f"- {cite(record.produced_artifacts[key])}")
    else:
        lines.append("- (none)")
    if record.stage_attempts:
        lines += ["", "## Stage attempts", ""]
        for stage_id in sorted(record.stage_attempts):
            lines.append(f"- {stage_id}: {record.stage_attempts[stage_id]}")
    if events:
        counts: dict[str, int] = {}
        for event in events:
            counts[event.event_type.value] = counts.get(event.event_type.value, 0) + 1
        lines += ["", "## Event summary", ""]
        for event_type in sorted(counts):
            lines.append(f"- {event_type}: {counts[event_type]}")
    lines.append("")
    return "\n".join(lines)
