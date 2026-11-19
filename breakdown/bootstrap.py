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

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from breakdown.approvals import ApprovalManager
from breakdown.artifact_store import ArtifactStore
from breakdown.bindings import BackendBindingStore, BindingNotValid, validate_binding
from breakdown.contracts import (
    CodingBackend,
    ContractRegistry,
    RoleBackend,
    build_contract_registry,
    validate_alignment,
    validate_definition_consistency,
)
from breakdown.engine import EngineStores, WorkflowEngine, load_workflow
from breakdown.events import EventStore
from breakdown.models import ContractKind, Settings, WorkflowDefinition
from breakdown.roles import RoleToolkit
from breakdown.roles.auditor import Auditor
from breakdown.roles.builder import Builder
from breakdown.roles.coder import Coder
from breakdown.roles.planner import Planner
from breakdown.roles.researcher import Researcher
from breakdown.run_store import RunStore
from breakdown.safety import SafetyBoundary


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
    validate_definition_consistency(definition)
    return Application(
        definition=definition,
        contracts=contracts,
        roles=roles,
        bindings=bindings,
        settings=settings,
    )


class BootstrapError(RuntimeError):
    """Runtime construction failed (locked state or invalid configuration)."""


def _validate_binding_coverage(definition: WorkflowDefinition, bindings: BackendBindingStore) -> None:
    """Every role that owns a workflow stage must have a binding whose
    permitted_operations cover that stage's operation (data-driven from the
    definition; D33). The builder's coding backend is not a role binding."""
    role_operations: dict[str, set[str]] = {}
    for stage in definition.stages:
        if stage.kind is ContractKind.ROLE and stage.owner != "builder":
            role_operations.setdefault(stage.owner, set()).add(stage.operation)
    for role in sorted(role_operations):
        binding = bindings.for_role(role)
        if binding is None:
            raise BindingNotValid(f"role {role!r} has no backend binding")
        missing = role_operations[role] - set(binding.permitted_operations)
        if missing:
            raise BindingNotValid(
                f"binding {binding.binding_id}: permitted_operations missing {sorted(missing)} for role {role!r}"
            )


class LockfileGuard:
    """Single-writer guard for the state directory (D18).

    The lockfile is created atomically and stores the owning PID. A foreign
    lock aborts construction; a known-stale lock can be taken over with
    force=True. Crash recovery is explicit, never silent.
    """

    def __init__(self, state_root: Path) -> None:
        self.path = state_root / "lock"

    def acquire(self, *, force: bool = False) -> None:
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if not force:
                holder = self.path.read_text(encoding="utf-8").strip() or "unknown"
                raise BootstrapError(
                    f"state is locked by {holder} (lockfile {self.path}); "
                    "force-unlock only when the holder is known-stale"
                ) from None
            self.path.unlink()
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}")

    def release(self) -> None:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        if f"pid={os.getpid()}" in text:
            self.path.unlink()


@dataclass(frozen=True, slots=True)
class Runtime:
    """A fully wired Phase 2 runtime: engine over durable stores."""

    engine: WorkflowEngine
    stores: EngineStores
    approvals: ApprovalManager
    lock: LockfileGuard
    definition: WorkflowDefinition
    contracts: ContractRegistry
    bindings: BackendBindingStore
    settings: Settings


def build_runtime(
    settings: Settings,
    *,
    role_backend: RoleBackend | None = None,
    role_backends: Mapping[str, RoleBackend] | None = None,
    coding_backend: CodingBackend,
    offline_demo: bool = False,
    force_unlock: bool = False,
) -> Runtime:
    """Construct stores, lockfile guard, approvals, and the workflow engine.

    Backends are injected by the caller and are only constructed from
    approved, validation-passing binding records; ``offline_demo`` selects
    the scripted offline path (D26) and skips binding validation.
    ``role_backends`` maps role -> backend (two-model-team seam, D32);
    roles not listed fall back to ``role_backend``.
    """
    definition = load_workflow(settings.workflow_path)
    contracts = build_contract_registry(definition)
    validate_alignment(contracts, definition)
    validate_definition_consistency(definition)
    bindings = BackendBindingStore.load(settings.backend_bindings_path)
    if not offline_demo:
        for binding in bindings.all():
            validate_binding(binding)
        if bindings.all():
            _validate_binding_coverage(definition, bindings)
    target_root = settings.target_repo.resolve()
    state_root = (target_root / settings.state_root).resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    lock = LockfileGuard(state_root)
    lock.acquire(force=force_unlock)
    stores = EngineStores(
        artifacts=ArtifactStore(state_root),
        events=EventStore(state_root),
        runs=RunStore(state_root),
        safety=SafetyBoundary(target_root=target_root, state_root=state_root),
    )
    approvals = ApprovalManager(
        artifacts=stores.artifacts, events=stores.events, runs=stores.runs, definition=definition
    )

    def role_factory(sandbox: Path | None) -> Mapping[str, object]:
        def backend_for(role: str) -> RoleBackend:
            selected = (role_backends or {}).get(role) or role_backend
            if selected is None:
                raise BootstrapError(f"no backend available for role {role!r}")
            return selected

        toolkits = {
            role: RoleToolkit(role=role, root=target_root) for role in ("auditor", "researcher", "coder", "planner")
        }
        coder = Coder(backend=backend_for("coder"), tools=toolkits["coder"])
        return {
            "auditor": Auditor(backend=backend_for("auditor"), tools=toolkits["auditor"], coder=coder),
            "researcher": Researcher(backend=backend_for("researcher"), tools=toolkits["researcher"]),
            "planner": Planner(backend=backend_for("planner"), tools=toolkits["planner"]),
            "builder": Builder(backend=coding_backend, sandbox_root=sandbox or target_root),
        }

    engine = WorkflowEngine(
        definition=definition,
        contracts=contracts,
        stores=stores,
        approvals=approvals,
        role_factory=role_factory,
    )
    return Runtime(
        engine=engine,
        stores=stores,
        approvals=approvals,
        lock=lock,
        definition=definition,
        contracts=contracts,
        bindings=bindings,
        settings=settings,
    )


def build_live_backends(settings: Settings) -> tuple[dict[str, RoleBackend], CodingBackend]:
    """Live OpenAI-compatible backends (D30/D32): one shared client, per-role
    model tiers, canonical tool loop rooted at the target repository."""
    from breakdown.live_backend import (
        OpenAICompatibleCodingBackend,
        OpenAICompatibleRoleBackend,
        build_openai_client,
        resolve_model,
    )

    client = build_openai_client(settings)
    tool_root = settings.target_repo.resolve()
    role_backends: dict[str, RoleBackend] = {}
    for role in ("auditor", "researcher", "coder", "planner"):
        role_backends[role] = OpenAICompatibleRoleBackend(
            client=client,
            model=resolve_model(settings, role),
            tool_root=tool_root,
            max_tool_rounds=settings.api_max_tool_rounds,
        )
    coding: CodingBackend = OpenAICompatibleCodingBackend(client=client, model=resolve_model(settings, "builder"))
    return role_backends, coding
