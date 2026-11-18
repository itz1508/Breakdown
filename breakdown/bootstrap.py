"""Bootstrap: construct and register dependencies.

Bootstrap creates evaluated role implementations and registers them
under stable role names; a role cannot silently select another backend.
It never calls a role directly and never decides workflow progression.

Phase 1 shape: backends are injected (offline fakes in tests; no model
SDK dependency exists yet). Phase 2 grows bootstrap around the stores
(artifacts, runs, approvals, safety) and constructs backends only from
approved, validation-passing BackendBinding records.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from breakdown.bindings import BackendBindingStore, validate_binding
from breakdown.contracts import (
    CodingBackend,
    ContractRegistry,
    RoleBackend,
    build_contract_registry,
    validate_alignment,
)
from breakdown.engine import load_workflow
from breakdown.models import Settings, WorkflowDefinition
from breakdown.roles import RoleToolkit
from breakdown.roles.auditor import Auditor
from breakdown.roles.builder import Builder
from breakdown.roles.coder import Coder
from breakdown.roles.planner import Planner
from breakdown.roles.researcher import Researcher


@dataclass(frozen=True, slots=True)
class Application:
    definition: WorkflowDefinition
    contracts: ContractRegistry
    roles: Mapping[str, object]
    bindings: BackendBindingStore
    settings: Settings


def build_role_registry(
    *,
    settings: Settings,
    role_backend: RoleBackend,
    coding_backend: CodingBackend,
    sandbox_root: Path,
) -> dict[str, object]:
    target_root = settings.target_repo.resolve()
    toolkits = {
        role: RoleToolkit(role=role, root=target_root) for role in ("auditor", "researcher", "coder", "planner")
    }
    coder = Coder(backend=role_backend, tools=toolkits["coder"])
    return {
        "auditor": Auditor(backend=role_backend, tools=toolkits["auditor"], coder=coder),
        "researcher": Researcher(backend=role_backend, tools=toolkits["researcher"]),
        "planner": Planner(backend=role_backend, tools=toolkits["planner"]),
        "builder": Builder(backend=coding_backend, sandbox_root=sandbox_root),
    }


def bootstrap(
    settings: Settings,
    *,
    role_backend: RoleBackend,
    coding_backend: CodingBackend,
    sandbox_root: Path,
) -> Application:
    definition = load_workflow(settings.workflow_path)
    bindings = BackendBindingStore.load(settings.backend_bindings_path)
    # Fail fast: an invalid or stale binding record must never reach a role.
    for binding in bindings.all():
        validate_binding(binding)
    roles = build_role_registry(
        settings=settings,
        role_backend=role_backend,
        coding_backend=coding_backend,
        sandbox_root=sandbox_root,
    )
    contracts = build_contract_registry(definition)
    validate_alignment(contracts, definition)
    return Application(
        definition=definition,
        contracts=contracts,
        roles=roles,
        bindings=bindings,
        settings=settings,
    )
