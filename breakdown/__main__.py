"""Entry point for ``python -m breakdown``.

Phase 1 supports the offline ``--check`` command only: load and validate
the workflow definition, build the contract registry, and report
alignment. Run/resume commands arrive with the Phase 2 engine lifecycle.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from breakdown.contracts import ContractConfigurationError, build_contract_registry, validate_alignment
from breakdown.engine import WorkflowDefinitionError, load_workflow
from breakdown.models import Settings


def _run_check(settings: Settings) -> int:
    try:
        definition = load_workflow(settings.workflow_path)
        registry = build_contract_registry(definition)
        validate_alignment(registry, definition)
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
    print(f"contracts: {len(registry)} aligned, 0 mismatches")
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
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("Phase 1 supports --check only; run/resume arrive with Phase 2")
    workflow_path = Path(args.workflow) if args.workflow else None
    settings = Settings() if workflow_path is None else Settings(workflow_path=workflow_path)
    return _run_check(settings)


if __name__ == "__main__":
    sys.exit(main())
