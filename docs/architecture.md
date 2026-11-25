# Breakdown Architecture

**Scope:** implementation currently present on main. The target architecture proposal is linked separately and is not presented as deployed code.

## Context and goals

Breakdown turns a user request into a bounded, researched, approved, and synchronized repository change. The implementation is organized around four boundaries:

- The workflow definition declares the stages, owners, artifact dependencies, gates, and transition rules.
- Typed Python contracts validate stage inputs and outputs.
- The workflow engine owns progression, approvals, persistence coordination, budgets, recovery, and completion.
- The safety boundary isolates Builder changes and independently checks which paths may be synchronized.

The intended properties are durable run state, explicit user decisions, source-grounded planning, least-privilege tools, checkpointed execution, and completion claims limited by evidence.

## High-level design

~~~mermaid
flowchart TD
    User[User request and decisions] --> CLI[CLI: breakdown.__main__]
    CLI --> Boot[Bootstrap and dependency wiring]
    YAML[breakdown.yaml] --> Engine[WorkflowEngine]
    Boot --> Engine
    Boot --> Roles[Role registry]
    Boot --> Stores[Durable stores]
    Engine --> Contracts[Contract registry]
    Contracts --> Roles
    Roles --> Backend[Injected role / coding backends]
    Roles --> Tools[Canonical tools and role allowlists]
    Tools --> Safety[Safety containment]
    Engine --> Approvals[Approval manager]
    Engine --> Checkpoint[Source checkpoint]
    Engine --> Safety
    Safety --> Sandbox[Run-scoped sandbox]
    Safety --> Sync[Changed-path authorization and sync]
    Engine --> Stores
    Stores --> State[(Target/.breakdown)]
    Sync --> Target[Target repository]
    Engine --> Report[Completion record and report]
    Report --> CLI
~~~

## Current source layout

The repository currently uses a flat Python package, not the proposed future system/agent package split.

| Source | Responsibility |
|---|---|
| breakdown/__main__.py | CLI entry point: check, run, resume, decide, cancel, status, memory, and bot commands |
| breakdown.yaml | Sole executable workflow definition |
| breakdown/models.py | Strict Pydantic models, workflow settings, artifact references, stage I/O, run and event records |
| breakdown/contracts.py | Role/backend protocols, stage contracts, typed operation registry, output mapping and consistency validation |
| breakdown/engine.py | Definition validation, stage progression, run lifecycle, decisions, recovery and terminal handling |
| breakdown/bootstrap.py | Constructs roles, injects backends/tools, validates bindings, constructs stores and runtime |
| breakdown/roles/ | Auditor, Researcher, Planner, Builder and the Coder capability |
| breakdown/tools.py | Canonical typed tool registry, role allowlists, input validation and dispatch |
| breakdown/safety.py | Read containment, sandbox creation, independent changed-path detection, synchronization authorization and copy-back |
| breakdown/artifact_store.py | Immutable artifact revisions with digest verification |
| breakdown/events.py | Persistent workflow event records |
| breakdown/run_store.py | Versioned run records and competing-writer protection |
| breakdown/checkpoint.py and breakdown/canonical.py | Source checkpoint capture/freshness and canonical digests |
| breakdown/approvals.py and breakdown/completion.py | Recorded decisions and terminal outcome validation |
| breakdown/memory.py | Immutable cross-run memory documents; writes are runtime-owned |
| breakdown/live_backend.py and breakdown/demo.py | OpenAI-compatible live adapters and scripted offline-demo backends |
| breakdown/bot.py | Higher-level task-intake and event-streaming wrapper over the runtime |

Tests live in tests/. Offline role and safety evaluations live in evals/. Setup and CLI usage are covered in [Onboarding](onboarding.md) and [Operations](operations.md).

## Runtime data flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as CLI
    participant R as Runtime / Engine
    participant A as Artifact and Run Stores
    participant W as Role worker
    participant P as Approval manager
    participant S as Safety boundary
    participant B as Builder
    U->>C: run request
    C->>R: construct runtime and start run
    R->>A: pin workflow, checkpoint source, persist request
    loop stages until pause or terminal
        R->>W: validated typed input and processing plan
        W-->>R: typed output and artifact values
        R->>A: persist immutable artifacts and events
        alt user decision stage
            R->>P: create pending decision bound to current artifacts
            R-->>C: awaiting_decision
            U->>C: decide approve / decline / request_changes
            C->>R: record decision
        else build execution stage
            R->>S: verify authorization and preconditions
            S->>B: create isolated sandbox
            B-->>S: actual task results and sandbox changes
            S->>S: independently detect and authorize changed paths
            S-->>R: synchronization result
        end
    end
    R->>A: persist completion and report inputs
    R-->>C: terminal state or next pause
~~~

## Systems and integration points

### Workflow definition and contracts

The engine loads breakdown.yaml into validated workflow models. The contract registry is derived from the definition; it does not independently redefine stage owners, operations, requires, or produces. The CLI check command verifies alignment and consistency.

### Role and backend integration

Bootstrap injects backend implementations into role classes. Live role backends use an OpenAI-compatible chat API; Builder has a separate CodingBackend interface. Per-role model overrides are supported. Live operation is gated by BackendBinding records that validate permitted operations and evaluation evidence.

Current wiring detail: Bootstrap constructs Auditor, Researcher, Planner, and Builder as workflow role entries. It also constructs Coder and injects it into Auditor as a read-only code-analysis capability. This existing ownership agrees with the latest four-agent target; the migration changes its package location and definition source, not its authority into a fifth dispatched agent.

### Tools

breakdown/tools.py defines SDK-neutral typed tools. RoleToolkit exposes only the tool names allowed for a given role. Tool input schemas are validated before dispatch. Repository reads are constrained to the target root; .env files are denied to role tools. Deterministic operations such as source checkpoint capture, plan freeze/preflight, approval hashing, and synchronization authorization are runtime operations, not model-callable tools.

### Persistence and state

Runtime state is rooted at <target repository>/.breakdown by default. Artifact, event, run, and memory records use the existing SQLite-backed stores. Artifact references identify logical keys, revisions, and digests. Run records pin workflow identity/version/digest. A lockfile enforces single-writer access to a target's run state.

### Sandbox and synchronization

The safety boundary creates a run-scoped sandbox from checkpoint-listed source files. It detects added, modified, and deleted paths by inspecting the sandbox rather than trusting Builder-reported path lists. Runtime authorization checks the recorded user approval, frozen plan hash, source checkpoint, preflight result, task targets, changed paths, and integration evidence before authorized copy-back.

## Key decisions and trade-offs

| Decision | Benefit | Trade-off |
|---|---|---|
| YAML is the executable workflow authority | Stage order, ownership and gates are inspectable and validated | YAML changes require contract and consistency tests |
| Typed Pydantic contracts reject undeclared fields | Predictable handoffs and validation | Schema changes require coordinated updates |
| SQLite stores live under the target state directory | No separate database service; run state travels with the target workspace | Single-writer lock; operators must preserve .breakdown |
| Artifacts are immutable revisions with digests | Provenance, tamper detection and historical reads | More references and revision bookkeeping |
| Builder works in a checkpoint-derived sandbox | Target files are not modified during untrusted build work | Copy and hash cost; large repositories need checkpoint scope discipline |
| Runtime independently detects changed paths | Builder cannot authorize its own writes | Synchronization can be blocked when results or paths are unexpected |
| Offline demo and live backends are separate modes | Safe reproducible workflow tests without API credentials | Offline demo does not establish model quality or live endpoint compatibility |
| Live backends are OpenAI-compatible and binding-gated | Supports compatible endpoints without adding a provider package | Native provider-specific features are not implied |
| Per-role tool allowlists | Limits capabilities exposed to each role | New tools require explicit registration and authorization updates |

## Verification boundary

Offline pytest and evals prove local contracts, deterministic operations, and scripted safety cases. They do not prove live model judgment or a production API endpoint. Live probing and evaluation are separate tasks.

On the current `main` implementation, Bootstrap's `role_factory` returns Auditor, Researcher, Planner, and Builder; it does not register a `verifier` backend. Therefore `WorkflowEngine._post_build` computes `integration_valid` from Builder's `validation_results`. This is a self-report fallback, not independent verification. Since the implementation uses `all(...)`, an empty list also evaluates as true and must not be described as verified.

`tests/test_verification.py` injects fake verifier backends by replacing `role_factory`, which exercises the engine's verifier branch in tests. It does not establish default Bootstrap wiring or make `BREAKDOWN_MODEL_VERIFIER` effective. The `model_verifier` setting is currently unwired and is intentionally omitted from operator configuration examples.

The Safety boundary independently detects changed paths, but that is a path-integrity control, not an independent evaluation of implementation correctness. The target independent-validation operation is described in [Target Architecture and Workflow](current-architecture-workflow.md).

## Current implementation versus target direction

- Current implementation: breakdown/ flat modules, breakdown/roles/, breakdown.yaml with eight stages, and the current Bootstrap wiring described above.
- Proposed target: four agents (Auditor, Researcher, Planner, Builder), with Coder retained as an Auditor-owned read-only capability; a `shared/` + `agents/` + `system/` package split; YAML module-docstring agent definitions; and the revised workflow in [Target Architecture and Workflow](current-architecture-workflow.md). The source migration map and stale-path removal gate are in [Structure Migration](structure-migration.md).

Do not use the proposed layout as an onboarding description or claim that the package migration is already implemented.
