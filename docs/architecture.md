# Breakdown Architecture

## Composition and ownership

`breakdown/__main__.py` is the composition root. It creates the agent registry and passes the registry and approved system capabilities into the host-controlled runtime.

The package has five agent identities:

- Researcher: `breakdown/researcher/`
- Auditor: `breakdown/auditor/`
- Coder: `breakdown/coder/`
- Planner: `breakdown/planner/`
- Builder: `breakdown/planner/builder/`

Coder is independent, not an Auditor-owned sub-role. Builder is a separate agent identity placed under Planner's package path and does not call the shared model loop.

## Layer responsibilities

| Layer | Owns |
|---|---|
| Composition root | Agent construction and dependency assembly |
| `shared/` | Strict base types, cross-agent models, configuration schema/access and shared model-loop utilities |
| Agent packages | Agent-specific behavior, canonical `SKILL.md`, local tests |
| `system/runtime/` | Workflow orchestration, approvals, execution lifecycle, runtime validation and backend wiring |
| `system/storage/` | Artifact, event, run and checkpoint persistence; canonical digest utilities |
| `system/tools/` | Canonical tool definitions, dispatch and role-scoped access |
| `system/safety.py` | Path containment, sandbox protection, changed-path detection and synchronization authorization |
| `system/memory.py` | Cross-run memory persistence and lookup |

## Dependency direction

Agent implementations may depend on shared contracts and the injected system-tool interface. They must not import workflow runtime internals, storage implementations, or sibling agents. Runtime may construct and invoke agents through explicit contracts. System tools and storage must not import agent implementations.

Builder is intentionally excluded from `shared/model_loop.py`; it executes through its coding backend inside the authorized sandbox.

## Safety properties

- Runtime owns workflow progression and approval enforcement.
- Agents do not self-advance, self-approve, or authorize source effects.
- Builder writes only to the authorized sandbox and confirmed paths.
- The host independently inspects exported changes and authorizes synchronization.
- Independent validation is separate from Builder's reported checks.
- Durable records preserve artifact identity, revisions, hashes, decisions and verification evidence.

## Verification boundary

Package relocation and import correctness do not prove the new end-to-end workflow. Workflow transitions, durable-state migration, approval binding, Builder export/exit, independent validation, and retention require their own integration tests. Report those capabilities only when the implementation and tests establish them.
