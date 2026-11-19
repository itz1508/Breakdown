"""Entry point for ``python -m breakdown``.

Commands:
- ``--check``: offline definition + contract alignment validation (Phase 1).
- ``run REQUEST``: start a new run and advance until it pauses or completes.
- ``resume RUN_ID``: continue a stored run (cross-process by design).
- ``decide RUN_ID ACTION``: record a user decision for a pending approval.
- ``status RUN_ID``: print the deterministic Markdown run report.
- ``cancel RUN_ID``: route a non-terminal run to completion/cancelled.

Phase 2 ships offline backends only: mutating commands require
``--offline-demo`` (D26). Every invocation is stateless — all state lives
in the ``.breakdown/`` store under the target repo, guarded by a lockfile.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from breakdown.approvals import ApprovalError
from breakdown.bindings import BindingNotValid
from breakdown.bootstrap import BootstrapError, Runtime, build_live_backends, build_runtime
from breakdown.contracts import (
    RUNTIME_OWNED_KEYS,
    ContractConfigurationError,
    build_contract_registry,
    mapped_output_keys,
    validate_alignment,
    validate_definition_consistency,
)
from breakdown.demo import OfflineDemoCodingBackend, OfflineDemoRoleBackend
from breakdown.engine import EngineError, WorkflowDefinitionError, load_workflow
from breakdown.models import ContractKind, InitialRequest, RunRecord, Settings
from breakdown.reports import render_run_report


def _run_check(settings: Settings) -> int:
    try:
        definition = load_workflow(settings.workflow_path)
        registry = build_contract_registry(definition)
        validate_alignment(registry, definition)
        validate_definition_consistency(definition)
    except (WorkflowDefinitionError, ContractConfigurationError) as exc:
        print(f"check failed: {exc}")
        return 1
    print(f"workflow: {definition.workflow_id} (definition_version {definition.definition_version})")
    print(f"stages: {len(definition.stages)}")
    for stage in definition.stages:
        registry.get(stage.id)
        print(
            f"  {stage.order}. {stage.id} [{stage.kind.value}] "
            f"owner={stage.owner} operation={stage.operation} contract=aligned"
        )
    uncovered_total = 0
    for stage in definition.stages:
        if stage.kind is not ContractKind.ROLE:
            continue
        step_outputs = {str(key) for step in stage.runtime_steps for key in step.get("outputs", [])}
        covered = mapped_output_keys(stage.id) | step_outputs | set(RUNTIME_OWNED_KEYS)
        uncovered = sorted(set(stage.produces) - covered)
        if uncovered:
            uncovered_total += len(uncovered)
            print(f"  coverage: {stage.id} UNCOVERED {uncovered}")
    print(f"contracts: {len(registry)} aligned, 0 mismatches")
    print("definition consistency: vocabularies, events, ownership, authorization, sync, digests, budget policy ok")
    if uncovered_total:
        print(f"produces coverage: {uncovered_total} uncovered keys")
        return 1
    print("produces coverage: full (mappers + runtime steps + runtime-owned keys)")
    return 0


def _settings_from_args(args: argparse.Namespace) -> Settings:
    updates: dict[str, Any] = {}
    if getattr(args, "workflow", None):
        updates["workflow_path"] = Path(args.workflow)
    if getattr(args, "target", None):
        updates["target_repo"] = Path(args.target)
    if getattr(args, "state_root", None):
        updates["state_root"] = Path(args.state_root)
    if getattr(args, "bindings", None):
        updates["backend_bindings_path"] = Path(args.bindings)
    return Settings().model_copy(update=updates) if updates else Settings()


def _add_runtime_args(parser: argparse.ArgumentParser, *, mutating: bool) -> None:
    parser.add_argument("--workflow", default=None, help="path to breakdown.yaml")
    parser.add_argument("--target", default=None, help="target repository root (default: .)")
    parser.add_argument("--state-root", default=None, help="state directory under target (default: .breakdown)")
    parser.add_argument("--bindings", default=None, help="path to backend bindings JSON")
    parser.add_argument("--user", default="cli-user", help="user identity recorded with decisions")
    if mutating:
        parser.add_argument(
            "--offline-demo",
            action="store_true",
            help="use the scripted offline backends (no live API needed)",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="use live OpenAI-compatible backends (BREAKDOWN_API_BASE_URL/API_KEY/MODEL; bindings required)",
        )
        parser.add_argument("--force-unlock", action="store_true", help="take over a known-stale lockfile")


def _demo_request_text(settings: Settings, run_id: str | None, fallback: str) -> str:
    """Demo backends are scripted per request; on resume the stored
    initial_request artifact is the authoritative source of that text."""
    if run_id is None:
        return fallback
    from breakdown.artifact_store import ArtifactStore
    from breakdown.run_store import RunStore

    state_root = (settings.target_repo.resolve() / settings.state_root).resolve()
    loaded = RunStore(state_root).load(run_id)
    if loaded is None:
        return fallback
    _, record = loaded
    ref = record.produced_artifacts.get("initial_request")
    if ref is None:
        return fallback
    return ArtifactStore(state_root).get_model(InitialRequest, ref.artifact_key, ref.revision).text


def _build_runtime(args: argparse.Namespace, settings: Settings, run_id: str | None, fallback_text: str) -> Runtime:
    offline_demo = getattr(args, "offline_demo", False)
    live = getattr(args, "live", False)
    if offline_demo and live:
        raise BootstrapError("--offline-demo and --live are mutually exclusive")
    if live:
        return _build_live_runtime(args, settings)
    if not offline_demo:
        raise BootstrapError("no backend selected: pass --offline-demo (scripted) or --live (OpenAI-compatible API)")
    text = _demo_request_text(settings, run_id, fallback_text)
    return build_runtime(
        settings,
        role_backend=OfflineDemoRoleBackend(text),
        coding_backend=OfflineDemoCodingBackend(text),
        offline_demo=True,
        force_unlock=getattr(args, "force_unlock", False),
    )


def _build_live_runtime(args: argparse.Namespace, settings: Settings) -> Runtime:
    """Live path (D30/D33): bindings are mandatory evidence — produce them by
    running `evals/run.py --live` against the candidate endpoint first."""
    from breakdown.live_backend import LiveBackendError

    if not settings.backend_bindings_path or not Path(settings.backend_bindings_path).exists():
        raise BootstrapError(
            "live mode requires validated backend bindings (--bindings): run "
            "'python evals/run.py --live' against the candidate endpoint, then record "
            "BackendBinding records (see bindings.example.json)"
        )
    try:
        role_backends, coding_backend = build_live_backends(settings)
    except LiveBackendError as exc:
        raise BootstrapError(str(exc)) from exc
    return build_runtime(
        settings,
        role_backends=role_backends,
        coding_backend=coding_backend,
        force_unlock=getattr(args, "force_unlock", False),
    )


def _print_state(record: RunRecord) -> None:
    print(f"run: {record.run_id}")
    print(f"state: {record.state.value}")
    print(f"stage: {record.current_stage or '-'}")
    if record.terminal_outcome:
        print(f"outcome: {record.terminal_outcome}")
    if record.reason:
        print(f"reason: {record.reason}")
    print(f"cost: {record.tokens_used} tokens, {record.tool_calls_used} tool calls")


def _cmd_run(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    runtime = _build_runtime(args, settings, None, args.request)
    try:
        record = runtime.engine.start_run(args.request, user_identity=args.user)
        record = runtime.engine.advance(record.run_id)
        _print_state(record)
        return 0
    finally:
        runtime.lock.release()


def _cmd_resume(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    runtime = _build_runtime(args, settings, args.run_id, "")
    try:
        record = runtime.engine.advance(args.run_id)
        _print_state(record)
        return 0
    finally:
        runtime.lock.release()


def _cmd_decide(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    runtime = _build_runtime(args, settings, args.run_id, "")
    try:
        record = runtime.engine.record_decision(args.run_id, args.action, user_identity=args.user, reason=args.reason)
        _print_state(record)
        return 0
    finally:
        runtime.lock.release()


def _cmd_cancel(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    runtime = _build_runtime(args, settings, args.run_id, "")
    try:
        record = runtime.engine.cancel(args.run_id, reason=args.reason or "cancelled via CLI")
        _print_state(record)
        return 0
    finally:
        runtime.lock.release()


def _cmd_status(args: argparse.Namespace) -> int:
    """Read-only: opens the stores directly (no lock, no backends)."""
    from breakdown.events import EventStore
    from breakdown.run_store import RunStore

    settings = _settings_from_args(args)
    state_root = (settings.target_repo.resolve() / settings.state_root).resolve()
    if not state_root.exists():
        print(f"no state found at {state_root}; start a run first")
        return 1
    record = RunStore(state_root).load(args.run_id)
    if record is None:
        print(f"run {args.run_id} not found")
        return 1
    _, run_record = record
    events = EventStore(state_root).load(args.run_id)
    print(render_run_report(run_record, events=events))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="breakdown")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the workflow definition and contract alignment offline",
    )
    parser.add_argument(
        "--workflow",
        default=None,
        help="path to breakdown.yaml (default: BREAKDOWN_WORKFLOW_PATH or ./breakdown.yaml)",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_p = subparsers.add_parser("run", help="start a new run and advance until pause or completion")
    run_p.add_argument("request", help="the exact request text")
    _add_runtime_args(run_p, mutating=True)

    resume_p = subparsers.add_parser("resume", help="advance an existing stored run")
    resume_p.add_argument("run_id")
    _add_runtime_args(resume_p, mutating=True)

    decide_p = subparsers.add_parser("decide", help="record a user decision for a pending approval")
    decide_p.add_argument("run_id")
    decide_p.add_argument("action", choices=["approve", "decline", "request_changes", "cancel"])
    decide_p.add_argument("--reason", default="")
    _add_runtime_args(decide_p, mutating=True)

    cancel_p = subparsers.add_parser("cancel", help="route a non-terminal run to completion/cancelled")
    cancel_p.add_argument("run_id")
    cancel_p.add_argument("--reason", default="")
    _add_runtime_args(cancel_p, mutating=True)

    status_p = subparsers.add_parser("status", help="print the deterministic Markdown run report")
    status_p.add_argument("run_id")
    _add_runtime_args(status_p, mutating=False)

    args = parser.parse_args(argv)
    if args.check:
        if args.command:
            parser.error("--check cannot be combined with a command")
        workflow_path = Path(args.workflow) if args.workflow else None
        settings = Settings() if workflow_path is None else Settings(workflow_path=workflow_path)
        return _run_check(settings)
    if not args.command:
        parser.error("a command is required (run, resume, decide, cancel, status) or use --check")

    handlers = {
        "run": _cmd_run,
        "resume": _cmd_resume,
        "decide": _cmd_decide,
        "cancel": _cmd_cancel,
        "status": _cmd_status,
    }
    try:
        return handlers[args.command](args)
    except (
        BootstrapError,
        EngineError,
        ApprovalError,
        BindingNotValid,
        WorkflowDefinitionError,
        ContractConfigurationError,
    ) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
