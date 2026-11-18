"""Workflow engine: definition authority + (Phase 2) run lifecycle.

Phase 1 scope: load and validate the declarative definition, prove the
forward dependency graph is acyclic, validate loop-backs separately, and
resolve transitions. Run lifecycle (start/record_decision/resume/cancel)
lands in Phase 2 together with the storage owners.
"""

from __future__ import annotations

from collections.abc import Mapping
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

import yaml
from pydantic import ValidationError

from breakdown.models import ContractKind, WorkflowDefinition


class WorkflowDefinitionError(ValueError):
    """The declarative workflow definition is invalid."""


def _load_definition(path: Path) -> WorkflowDefinition:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowDefinitionError(f"workflow definition not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise WorkflowDefinitionError(f"workflow definition is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkflowDefinitionError("workflow definition must be a mapping")
    try:
        return WorkflowDefinition.model_validate(raw)
    except ValidationError as exc:
        raise WorkflowDefinitionError(f"workflow definition rejected by schema: {exc}") from exc


def _producers(definition: WorkflowDefinition) -> dict[str, str]:
    producers: dict[str, str] = {"initial_request": "<external>"}
    for stage in definition.stages:
        for key in stage.produces:
            producers.setdefault(key, stage.id)
        for action_outputs in stage.output_by_action.values():
            for key in action_outputs:
                producers.setdefault(key, stage.id)
        for step in stage.runtime_steps:
            outputs = step.get("outputs", [])
            if isinstance(outputs, list):
                for key in outputs:
                    producers.setdefault(str(key), stage.id)
    return producers


def _validate_orders(definition: WorkflowDefinition) -> None:
    orders = [stage.order for stage in definition.stages]
    if sorted(orders) != list(range(1, len(orders) + 1)):
        raise WorkflowDefinitionError("stage orders must be unique and contiguous from 1")
    ids = definition.stage_ids()
    if len(ids) != len(set(ids)):
        raise WorkflowDefinitionError("stage ids must be unique")


def _validate_forward_edges(definition: WorkflowDefinition) -> None:
    """Artifact-dependency DAG over stages; cycles are rejected."""
    producers = _producers(definition)
    graph: dict[str, set[str]] = {stage.id: set() for stage in definition.stages}
    for stage in definition.stages:
        for key in stage.requires:
            producer = producers.get(key)
            if producer is None:
                raise WorkflowDefinitionError(f"{stage.id}: requires unproduced artifact {key!r}")
            if producer != "<external>" and producer != stage.id:
                graph[stage.id].add(producer)
    sorter: TopologicalSorter[str] = TopologicalSorter(graph)
    try:
        sorter.prepare()
    except CycleError as exc:
        raise WorkflowDefinitionError(f"forward dependency graph is cyclic: {exc}") from exc


def _validate_loop_backs(definition: WorkflowDefinition) -> None:
    """Loop-back transitions are validated separately from the forward DAG:
    existing earlier target, finite attempts, declared invalidation, and no
    loop-back originating from a non-decision stage."""
    stage_ids = set(definition.stage_ids())
    orders = {stage.id: stage.order for stage in definition.stages}
    for stage in definition.stages:
        changes = stage.transitions.get("on_request_changes")
        if changes is None:
            continue
        if not isinstance(changes, Mapping):
            raise WorkflowDefinitionError(f"{stage.id}: on_request_changes must be a mapping")
        target = changes.get("return_to")
        if not isinstance(target, str) or target not in stage_ids:
            raise WorkflowDefinitionError(f"{stage.id}: loop-back target {target!r} does not exist")
        if orders[target] >= orders[stage.id]:
            raise WorkflowDefinitionError(f"{stage.id}: loop-back must return to an earlier stage")
        max_loops = changes.get("max_loops")
        if not isinstance(max_loops, int) or max_loops < 1:
            raise WorkflowDefinitionError(f"{stage.id}: loop-back requires a finite max_loops >= 1")
        if not changes.get("invalidate"):
            raise WorkflowDefinitionError(f"{stage.id}: loop-back must declare invalidated artifacts")
        if stage.kind is not ContractKind.DECISION:
            raise WorkflowDefinitionError(f"{stage.id}: only decision stages may loop back")
    declared = definition.dependency_validation.get("loop_back_edges", [])
    if isinstance(declared, list):
        for edge in declared:
            if not isinstance(edge, Mapping):
                raise WorkflowDefinitionError("loop_back_edges entries must be mappings")
            if edge.get("from") not in stage_ids or edge.get("to") not in stage_ids:
                raise WorkflowDefinitionError(f"declared loop-back edge does not resolve: {dict(edge)}")


def load_workflow(path: str | Path) -> WorkflowDefinition:
    """Load, type-validate, and structurally validate the workflow definition."""
    definition = _load_definition(Path(path))
    _validate_orders(definition)
    _validate_forward_edges(definition)
    _validate_loop_backs(definition)
    return definition


def resolve_next_stage(definition: WorkflowDefinition, current_id: str, *, action: str | None = None) -> str | None:
    """Resolve the forward transition from the current stage.

    Decision stages require the declared action; role/deterministic stages
    follow their declared ``next`` or positional order. Terminal stages
    resolve to None.
    """
    stage = definition.get_stage(current_id)
    if stage.kind is ContractKind.DECISION:
        if action is None:
            raise WorkflowDefinitionError(f"decision stage {current_id!r} requires an action to resolve")
        target = stage.transitions.get(f"on_{action}")
        if isinstance(target, Mapping):
            target = target.get("return_to")
        if not isinstance(target, str):
            raise WorkflowDefinitionError(f"{current_id}: no transition declared for action {action!r}")
        return target
    if stage.next:
        return stage.next
    following = [candidate for candidate in definition.stages if candidate.order == stage.order + 1]
    return following[0].id if following else None
