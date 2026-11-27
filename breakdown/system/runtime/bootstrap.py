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
from typing import Any, Literal
from breakdown.shared.models import CodingBackend, ContractKind, RoleBackend, Settings, WorkflowDefinition
from breakdown.system.memory import MemoryStore
from breakdown.system.runtime.approvals import ApprovalManager
from breakdown.system.runtime.bindings import BackendBindingStore, BindingNotValid, validate_binding
from breakdown.system.runtime.contracts import (
    build_contract_registry,
    ContractRegistry,
    validate_alignment,
    validate_definition_consistency,
)
from breakdown.system.runtime.engine import EngineStores, WorkflowEngine, load_workflow
from breakdown.system.safety import SafetyBoundary
from breakdown.system.storage.artifact_store import ArtifactStore
from breakdown.system.storage.events import EventStore
from breakdown.system.storage.run_store import RunStore
from breakdown.system.tools.toolkit import RoleToolkit

@dataclass(frozen=True, slots=True)
class Application:
    definition: WorkflowDefinition
    contracts: ContractRegistry
    roles: Mapping[str, object]
    bindings: BackendBindingStore
    settings: Settings


def _resolve_agent_types(agent_types: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if agent_types is not None:
        return agent_types
    from breakdown.__main__ import AGENT_TYPES
    return AGENT_TYPES


def build_role_registry(
    *,
    settings: Settings,
    role_backend: RoleBackend,
    coding_backend: CodingBackend,
    sandbox_root: Path,
    agent_types: Mapping[str, Any] | None = None,
    memory_root: Path | None = None,
    verifier_backend: RoleBackend | None = None,
) -> dict[str, object]:
    target_root = settings.target_repo.resolve()
    classes = _resolve_agent_types(agent_types)
    toolkits = {
        role: RoleToolkit(role=role, root=target_root, memory_root=memory_root)
        for role in ("auditor", "researcher", "coder", "planner")
    }
    roles: dict[str, object] = {
        "auditor": classes["auditor"](backend=role_backend, tools=toolkits["auditor"]),
        "researcher": classes["researcher"](backend=role_backend, tools=toolkits["researcher"]),
        "coder": classes["coder"](backend=role_backend, tools=toolkits["coder"]),
        "planner": classes["planner"](backend=role_backend, tools=toolkits["planner"]),
        "builder": classes["builder"](backend=coding_backend, sandbox_root=sandbox_root),
    }
    if verifier_backend is not None:
        roles["verifier"] = verifier_backend
    return roles


def bootstrap(
    settings: Settings,
    *,
    role_backend: RoleBackend,
    coding_backend: CodingBackend,
    sandbox_root: Path,
    agent_types: Mapping[str, Any] | None = None,
    verifier_backend: RoleBackend | None = None,
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
        agent_types=agent_types,
        verifier_backend=verifier_backend,
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


def _validate_binding_coverage(
    definition: WorkflowDefinition,
    bindings: BackendBindingStore,
    *,
    additional_role_operations: Mapping[str, set[str]] | None = None,
) -> None:
    """Every role that owns a workflow stage must have a binding whose
    permitted_operations cover that stage's operation (data-driven from the
    definition; D33). The builder's coding backend is not a role binding."""
    role_operations: dict[str, set[str]] = {}
    for stage in definition.stages:
        if stage.kind is ContractKind.ROLE and stage.owner != "builder":
            role_operations.setdefault(stage.owner, set()).add(stage.operation)
    for role, operations in (additional_role_operations or {}).items():
        role_operations.setdefault(role, set()).update(operations)
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
    role_backends: Mapping[str, Any] | None = None
    coding_backend: Any | None = None

    def close(self) -> None:
        """Synchronously release lockfile and close resources (D43)."""
        self.lock.release()

    async def aclose(self) -> None:
        """Asynchronously close backend clients and release lockfile (D43)."""
        if self.role_backends:
            for b in self.role_backends.values():
                if hasattr(b, "aclose"):
                    await b.aclose()
                elif hasattr(b, "close"):
                    b.close()
        if self.coding_backend is not None:
            if hasattr(self.coding_backend, "aclose"):
                await self.coding_backend.aclose()
            elif hasattr(self.coding_backend, "close"):
                self.coding_backend.close()
        self.lock.release()


def build_runtime(
    settings: Settings,
    *,
    role_backend: RoleBackend | None = None,
    role_backends: Mapping[str, RoleBackend] | None = None,
    coding_backend: CodingBackend,
    offline_demo: bool = False,
    runtime_kind: Literal["offline_demo", "live_openai"] | None = None,
    force_unlock: bool = False,
    agent_types: Mapping[str, Any] | None = None,
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
        _validate_binding_coverage(
            definition,
            bindings,
            additional_role_operations={"verifier": {"verify_build_task"}},
        )
        if role_backends is None or role_backends.get("verifier") is None:
            raise BootstrapError(
                "live runtime requires a separately injected independent verifier backend"
            )
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
        memory=MemoryStore(state_root),
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

        classes = _resolve_agent_types(agent_types)
        toolkits = {
            role: RoleToolkit(role=role, root=target_root, memory_root=state_root)
            for role in ("auditor", "researcher", "coder", "planner")
        }
        roles: dict[str, object] = {
            "auditor": classes["auditor"](backend=backend_for("auditor"), tools=toolkits["auditor"]),
            "researcher": classes["researcher"](backend=backend_for("researcher"), tools=toolkits["researcher"]),
            "coder": classes["coder"](backend=backend_for("coder"), tools=toolkits["coder"]),
            "planner": classes["planner"](backend=backend_for("planner"), tools=toolkits["planner"]),
            "builder": classes["builder"](backend=coding_backend, sandbox_root=sandbox or target_root),
        }
        # The verifier is independent of the Builder and is never inherited from the shared
        # role backend. A missing verifier remains missing and blocks synchronization.
        verifier_backend = (role_backends or {}).get("verifier")
        if verifier_backend is None and offline_demo:
            # Offline demo supplies a deterministic verifier over actual sandbox observations.
            verifier_backend = role_backend
        if verifier_backend is not None:
            roles["verifier"] = verifier_backend
        return roles

    resolved_kind = runtime_kind
    if resolved_kind is None and offline_demo:
        resolved_kind = "offline_demo"

    engine = WorkflowEngine(
        definition=definition,
        contracts=contracts,
        stores=stores,
        approvals=approvals,
        role_factory=role_factory,
        runtime_kind=resolved_kind,
    )
    effective_backends: dict[str, Any] = dict(role_backends or {})
    if role_backend is not None:
        effective_backends.setdefault("default", role_backend)

    return Runtime(
        engine=engine,
        stores=stores,
        approvals=approvals,
        lock=lock,
        definition=definition,
        contracts=contracts,
        bindings=bindings,
        settings=settings,
        role_backends=effective_backends,
        coding_backend=coding_backend,
    )


def build_live_backends(settings: Settings) -> tuple[dict[str, RoleBackend], CodingBackend]:
    """Live OpenAI-compatible backends (D30/D32): one shared client, per-role
    model tiers, canonical tool loop rooted at the target repository."""
    from breakdown.system.runtime.live_backend import (
        LiveBackendError,
        OpenAICompatibleCodingBackend,
        OpenAICompatibleRoleBackend,
        build_openai_client,
        resolve_model,
    )

    if not settings.model_verifier:
        raise LiveBackendError(
            "live build execution requires an independent verifier model "
            "(BREAKDOWN_MODEL_VERIFIER)"
        )
    builder_model = resolve_model(settings, "builder")
    verifier_model = resolve_model(settings, "verifier")
    if verifier_model == builder_model:
        raise LiveBackendError(
            "BREAKDOWN_MODEL_VERIFIER must differ from the Builder model "
            "to preserve independent evaluation"
        )

    client = build_openai_client(settings)
    tool_root = settings.target_repo.resolve()
    role_backends: dict[str, RoleBackend] = {}
    for role in ("auditor", "researcher", "coder", "planner", "verifier"):
        role_backends[role] = OpenAICompatibleRoleBackend(
            client=client,
            model=verifier_model if role == "verifier" else resolve_model(settings, role),
            tool_root=tool_root,
            max_tool_rounds=settings.api_max_tool_rounds,
        )
    coding: CodingBackend = OpenAICompatibleCodingBackend(client=client, model=builder_model)
    return role_backends, coding
