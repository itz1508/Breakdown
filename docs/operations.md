# Operations Guide

Common operator procedures for the current CLI.

## Command reference

Run commands from the Breakdown project root.

| Command | Purpose | Mutates run state? |
|---|---|---|
| python -m breakdown --check | Validate workflow YAML, generated stage contracts, consistency and output coverage | No |
| python -m breakdown run REQUEST | Start a new run and advance until a decision or terminal state | Yes |
| python -m breakdown decide RUN_ID ACTION | Record an action for the pending decision | Yes |
| python -m breakdown resume RUN_ID | Continue a stored run | Yes |
| python -m breakdown cancel RUN_ID | Cancel a non-terminal run through Completion | Yes |
| python -m breakdown status RUN_ID | Render the deterministic Markdown report from stores | No |
| python -m breakdown memory list | List cross-run memory heads | No |
| python -m breakdown memory show PATH | Read a memory revision | No |
| python -m breakdown bot TASK --stream | Run through the event-driven Bot wrapper and print events | Yes |

The run/resume/decide/cancel commands require --offline-demo or --live. For the Bot command, --offline-demo selects scripted backends; without it, the Bot constructs live backends and therefore needs live endpoint configuration and valid bindings. Use --workflow, --target, --state-root and --bindings when you need to override defaults. The exact parser and flags are in breakdown/__main__.py.

## Walkthrough: execute an offline run

1. Validate the workflow:

       uv run --no-sync python -m breakdown --check

2. Start a run against a disposable target:

       uv run --no-sync python -m breakdown run "Create a small demo change" --workflow ./breakdown.yaml --target ./demo-target --offline-demo

3. Save the printed run ID.
4. Inspect the pending stage and report:

       uv run --no-sync python -m breakdown status RUN_ID --target ./demo-target

5. Record the action offered by the pending gate:

       uv run --no-sync python -m breakdown decide RUN_ID approve --workflow ./breakdown.yaml --target ./demo-target --offline-demo

6. Resume the run:

       uv run --no-sync python -m breakdown resume RUN_ID --workflow ./breakdown.yaml --target ./demo-target --offline-demo

7. Repeat status → decide → resume when the workflow pauses at the next user decision. Do not assume a run completed because a role returned a result.

## Walkthrough: inspect a run

The status command reads persisted run and event records without constructing model backends or acquiring the mutating-run lock.

    uv run --no-sync python -m breakdown status RUN_ID --target ./demo-target

The report includes run state, current stage, terminal outcome/reason when present, session and pinned workflow definition, token/tool usage, produced artifact refs, stage attempts, stage cost and event summary.

## Walkthrough: recover a paused or interrupted run

1. Run status to inspect the current durable state.
2. Check whether the process that owned the target lock is still running.
3. If it is still active, do not start a competing mutating command.
4. If the lock is confirmed stale, resume with --force-unlock:

       uv run --no-sync python -m breakdown resume RUN_ID --workflow ./breakdown.yaml --target ./demo-target --offline-demo --force-unlock

5. Inspect the resulting state and completion report.

Force-unlock removes a lock only after an explicit operator decision. Do not use it to bypass a live process.

## Walkthrough: cancel

    uv run --no-sync python -m breakdown cancel RUN_ID --workflow ./breakdown.yaml --target ./demo-target --offline-demo --reason "Operator requested cancellation"

Cancellation is routed through the engine's completion path so the terminal record can retain the reason and available evidence.

## Walkthrough: inspect cross-run memory

    uv run --no-sync python -m breakdown memory list --target ./demo-target
    uv run --no-sync python -m breakdown memory show lessons/RUN_ID.md --target ./demo-target

Memory list/show are read-only operations. Runtime owns memory writes and lesson retention. Treat memory as prior experience, not as authority that overrides current source or a current user decision.

## Operational cautions

- Keep .breakdown/ with the target workspace. It contains durable run state, artifacts, events, checkpoints, memory and lock state.
- Do not manually edit SQLite files or artifact records.
- Never copy a sandbox into the target manually; synchronization must pass through the safety boundary.
- Do not report completion from Builder output alone. Read the terminal run outcome and associated evidence.
- The Bot wrapper exposes event streaming and intent routing, but its task parsing is a separate interface from the declarative eight-stage workflow. Use run/resume/decide when you need direct control over stage gates.
- --auto-approve exists on the Bot CLI. Use it only in a controlled environment with an explicit policy decision; it bypasses interactive decision handling.
