# Anthropic SDK Tooling — Breakdown Gap Review

**Review date:** 2026-11-24  
**Breakdown baseline:** [`955050197725`](https://github.com/itz1508/Breakdown/commit/95505019772544329fa9f9ab3d9148d232cf7b56) on `main`  
**Reference baseline:** Anthropic Python SDK 2.13.0, [`bda18c620dbe`](https://github.com/anthropics/anthropic-sdk-python/commit/bda18c620dbec4c7febed947d7b8367d84c9171d)  
**Review type:** Read-only source and test inspection. No runtime implementation or tests were changed or executed.

## Executive assessment

Breakdown already has the right starting ownership model for canonical tools: one SDK-neutral registry, Pydantic input models, role-specific allowlists, a runtime-owned workflow engine, a separate Builder coding backend, and durable workflow events.

The important gaps are not a lack of another registry or a need to copy Anthropic's toolset hierarchy. The main gap is that the live provider adapter currently owns both the provider turn and the multi-round tool loop, including direct tool dispatch. This makes provider integration responsible for orchestration concerns that should be shared above the provider boundary. The same path invokes synchronous tool handlers inline from an async method, so a blocking handler can block the event loop.

The recommended direction is to preserve Breakdown's existing canonical registry and Runtime authority, then separate these responsibilities:

1. Provider adapter: one model turn and provider response normalization.
2. Shared Agent execution loop: bounded model/tool rounds and Agent-level call lifecycle.
3. Middleware: per-model-call and per-tool-call Input → Wrap → Output interception; not a second workflow engine and not a substitute for the Agent loop.
4. Host/Runtime: immutable caller identity and tool grants, workflow transitions, user approvals, budgets, persistence, and source-side effects.
5. Canonical tool definitions and dispatch: one source of truth for schemas, input validation, authorization metadata, handler binding, and typed results.

This is a design review, not an implementation authorization.

## 1. Current Breakdown architecture (verified)

The inspected `main` tree has the following relevant ownership:

| Concern | Current source | Observed responsibility |
|---|---|---|
| Workflow authority | `breakdown/engine.py`, `breakdown/contracts.py`, `breakdown.yaml` | WorkflowEngine advances contracts/stages, activates roles, applies timeouts, and stops at decisions or terminal states. |
| Canonical model-callable tools | `breakdown/tools.py` | One SDK-neutral `TOOLS` mapping of `CanonicalTool` definitions; typed Pydantic input models and handler functions. |
| Role grants | `breakdown/tools.py`, `breakdown/roles/__init__.py` | `ROLE_TOOL_ALLOWLIST` and `RoleToolkit` expose a role-specific subset; Builder receives no canonical tool grant. |
| Provider tool schema/loop | `breakdown/live_backend.py` | `tool_schemas()` derives provider schemas from the canonical registry. `OpenAICompatibleRoleBackend.generate()` owns bounded tool rounds, call dispatch, and final structured output. |
| Runtime construction/resources | `breakdown/bootstrap.py` | Runtime constructs/injects shared provider clients and role backends; async close releases clients and the run lock. |
| Build capability | `breakdown/roles/builder.py`, `breakdown/live_backend.py`, `breakdown/safety.py` | Builder uses a separate CodingBackend/sandbox path rather than canonical model-callable tools. |
| Durable workflow events | `breakdown/events.py`, `breakdown/models.py` | SQLite append-only events, canonical digest verification, persistent workflow events and non-persisted activity updates. |
| Cross-run memory | `breakdown/memory.py`, `breakdown/tools.py` | Memory writes are runtime-owned; selected analysis roles get read-only memory tools. |
| Tests | `tests/test_tools.py`, `tests/test_live_backend.py`, `tests/test_events.py`, `tests/test_roles.py` | Registry/allowlist, provider loop, schema, containment, event persistence and role boundary behavior. |

The live repository does **not** currently contain a `breakdown/agent/`, `breakdown/mcp/`, or hooks package. `PLANS.md` records the shared Agent middleware direction as a future design decision; it is not an implemented source path in this baseline. The current plan also treats MCP/plugin deployment separation as a later phase gated by evidence.

## 2. Coverage matrix

Statuses refer to the inspected source at the baseline commit above, not to intended future behavior.

| Capability / pattern | Status | Breakdown evidence and gap |
|---|---|---|
| One canonical tool registry | **Covered** | `TOOLS` is the single SDK-neutral registry. Keep it; do not add a parallel Tool Capability Catalog or second dispatch registry. |
| Typed tool inputs and generated schemas | **Covered** | Each `CanonicalTool` has an `input_model`; `tool_definitions()` and `tool_schemas()` derive provider schemas from it; dispatch validates with Pydantic. |
| Role-specific tool grants | **Partial** | `ROLE_TOOL_ALLOWLIST`, `RoleToolkit.call()`, and the provider's `call.function.name not in allowed` check enforce the normal role path. The final `dispatch_tool()` API itself receives no Host-bound principal/capability context, so the grant is not independently re-established at the canonical dispatch boundary. This is a defense-in-depth and future-adapter boundary gap, not evidence that the current allowlist is absent. |
| Typed tool results | **Partial** | `CanonicalTool` defines an input model but no output model/result validator. Handler results vary; some are Pydantic models and some are dynamically shaped values. The provider adapter serializes them generically. |
| Shared bounded Agent tool loop | **Gap** | `OpenAICompatibleRoleBackend.generate()` contains the multi-round loop, dispatches calls, accumulates usage and shapes the final answer. A second provider would likely duplicate this orchestration. |
| Provider adapter boundary | **Partial** | Schema conversion and client injection are already adapter concerns, but turn-level orchestration and canonical dispatch remain inside the OpenAI-compatible adapter. |
| Non-blocking tool invocation | **Gap** | The async backend calls synchronous `_dispatch()` inline. Canonical handlers are synchronous; for example, `web_search()` uses blocking `httpx.Client`. A slow handler can block the event loop and delay other tasks and timeout handling. |
| Normalized tool errors/results | **Partial** | The adapter catches broad exceptions and sends `{"error": str(exc)}`; model-returned content is serialized directly. There is no canonical discriminated result/error envelope or central output validation/normalization boundary. |
| Per-tool-call durable evidence | **Partial** | Workflow stages and artifacts are durable and digest-checked. Event types do not currently represent tool-call requested/started/completed/errored or a posted/acknowledged result. This is not required for today's in-process CLI loop, but would matter for retries, precise audit, or remote event-driven execution. |
| Tool resource lifecycle | **Partial / low current need** | Runtime closes provider clients. Canonical tools are currently mostly stateless functions and have no uniform per-tool close/context-manager lifecycle. Do not add lifecycle machinery until a real stateful tool needs it. |
| Multi-member toolset/family registry | **Not currently applicable** | Breakdown's current canonical tools are standalone functions, not browser/computer-style stateful families. Anthropic's family/member model should not be transplanted pre-emptively. |
| Managed remote-session event reconciliation | **Not currently applicable** | Breakdown uses durable run state and stateless CLI invocations that pause/resume across processes; it does not currently consume a remote provider session event stream. |
| File/path confinement | **Covered for current tool scope** | Breakdown routes source reads through its own containment policy and tests path escape and secret-file rejection. Anthropic's explicit context/path resolution is a useful comparison, not a replacement for Breakdown's SafetyBoundary or sandbox. |
| MCP adapter boundary | **Not implemented in current tree** | Anthropic's `mcp.py` wraps MCP definitions/calls as runnable provider tools. Breakdown's current `main` has no MCP package; preserve the existing single canonical registry if/when MCP adapters are introduced. |
| Middleware interception | **Planned, not implemented** | `PLANS.md` records Input → Wrap → Output middleware around model and tool call boundaries. Keep it call-scoped; do not let middleware own workflow transitions, approval decisions, or the Agent's bounded loop. |

## 3. Patterns worth retaining from Anthropic

### 3.1 Shared dispatch mechanics, not the Messages runner

Anthropic factors reusable dispatch mechanics into `_tool_dispatch.py`: sync/async handling, runnable invocation, result/error normalization, and indexing. Both its Messages and managed-session runners consume these helpers.

The useful lesson is to share the *call mechanics* and keep protocol-specific loops in their own layer. Its Messages `BetaToolRunner` implements stop-reason handling, history changes, compaction, eager calls, and provider-specific behavior. That is not a suitable shared Breakdown Agent loop. Breakdown's shared loop should be provider-neutral and materially smaller.

### 3.2 Explicit member metadata and schema drift checks

Anthropic's `Member` and `Registry` associate a member name with its input model and result metadata. Browser/computer member input names/types are derived from generated API unions, while hand-maintained metadata is checked against those generated definitions to detect drift.

For Breakdown, retain `CanonicalTool` as the only registry. Add fields such as output model, risk/confirmation policy, or capability requirements only when a concrete Breakdown tool needs them. Add consistency tests tying registry metadata, provider schema output, and dispatch behavior together. Reject duplicate canonical names rather than copying Anthropic's “later registration wins” behavior.

### 3.3 Runtime-created context and capability injection

Anthropic's `AgentToolContext` demonstrates explicit dependency/context injection: file tools close over a supplied working directory and path policy rather than repeatedly resolving ambient state. Breakdown already injects roots and shared clients through Runtime/bootstrap.

The Breakdown-specific refinement is stronger: the Runtime should construct a frozen call context containing the run/session/role identity, permitted canonical tool names or capability IDs, root references, limits, and only the dependencies needed for that call. A model-produced tool name or argument must never be able to change that identity or expand its grants. Handlers should receive injected clients and settings; they should not independently read credentials or invent a new client.

Do not copy Anthropic's broad mutable context wholesale. In particular, its documentation explicitly notes that the Bash tool is unrestricted by the file-tool path policy and needs OS-level containment. Path allowlists alone are not shell containment.

### 3.4 Reconcile observed events against acknowledged results

The managed-session runner distinguishes an event being observed (`_seen`) from a result being acknowledged (`_answered`). It opens the stream before reading history, deduplicates overlap, retries seen-but-unanswered calls, and refuses to dispatch from incomplete history.

This is a strong pattern **if** Breakdown later adopts a remote event stream or asynchronous external tool executor. It is not a reason to turn today's local, bounded request/response loop into a session service. If that future transition happens, define durable call identity, execution result, result-post acknowledgement, and reconciliation semantics before adding retries: re-running an external side effect merely because its result acknowledgement was lost can duplicate the side effect.

### 3.5 Resource lifecycle must match the runner

Anthropic's SDK explicitly has different cleanup behavior across its Messages and Sessions runners. Stateful tools can own close hooks/context managers, but a consumer must verify that its runner actually drives them.

Breakdown currently closes provider clients at Runtime shutdown. Keep that simple while canonical tools remain stateless. If a handler later owns a subprocess, browser, or connection, specify its scope (per call, per Agent, or per run), cleanup on success/error/timeout/cancellation, and tests for each path before adding a generic lifecycle API.

### 3.6 MCP is an adapter, not another authority

Anthropic's `mcp.py` adapts an MCP tool definition and client session to the SDK's runnable function-tool interface. The MCP transport/client does not thereby become a second application-level capability registry.

For Breakdown, a future MCP integration should adapt discovered MCP tools into the existing canonical definitions and Host authorization/dispatch route. Preserve the repository's eventual MCP package conventions when it is actually introduced; do not create an additional independent tool execution loop.

## 4. Recommended target boundaries

```text
WorkflowEngine / Runtime (Host authority)
  |-- owns run/session/role identity, approvals, budgets, state and progression
  |-- constructs immutable ToolCallContext and grants
  |
Agent execution loop (shared, provider-neutral)
  |-- bounded model/tool rounds
  |-- invokes provider adapter for one model turn
  |-- coordinates per-call middleware
  |
  +--> Provider adapter
  |      one request/response turn; normalize provider tool calls and usage
  |
  +--> Middleware chain
  |      Input -> Wrap -> Output around model calls and tool calls
  |
  +--> existing CanonicalTool registry / dispatch
         resolve -> authorize -> validate input -> execute -> validate result
         -> normalize error/result -> emit bounded evidence
```

This diagram describes responsibility boundaries, not a mandate to create every box as a separate module. Reuse the existing source files and approved Agent middleware direction. In particular:

- The existing `TOOLS` registry remains canonical; no second catalogue or router.
- The provider adapter should not own workflow/session authority or the shared bounded Agent loop.
- Middleware sees/intercepts a call; it cannot mint identity, widen permissions, approve a plan, advance a workflow, or synchronize files.
- Authorization should be checked at the dispatch boundary using Host-created context, even when the provider adapter has already restricted the offered tool list.
- Builder remains on its separate CodingBackend and approved sandbox path; do not expose Builder with a general canonical tool allowlist.
- Runtime remains the only owner of durable writes, cross-run memory writes, approvals, synchronization, and workflow transitions.

## 5. Prioritized gap closure

| Priority | Recommendation | Why / acceptance condition |
|---|---|---|
| P0 | Move synchronous tool execution off the async event loop, or convert genuinely I/O-bound tools to async handlers. | A deliberately blocking test handler must not stall an unrelated coroutine; cancellation/timeout semantics must be explicit. |
| P1 | Extract a small provider-neutral Agent tool loop; reduce each provider adapter to one-turn request/response normalization. | A fake provider and the current OpenAI-compatible provider must execute the same bounded loop without duplicating dispatch logic. |
| P1 | Pass an immutable Host-created call context into the canonical dispatch boundary and enforce its grants there. | Tests must show a forged model tool call cannot alter caller identity, role, roots, or allowed tools; unknown and unauthorized names are rejected before handler invocation. |
| P1 | Add optional typed output models and one normalized result/error representation to the existing canonical tool definition/dispatch path. | Malformed handler output is rejected; expected tool errors are represented distinctly from unexpected execution exceptions; provider serialization is deterministic and bounded. |
| P2 | Add call-level lifecycle events/trace attributes only where audit or recovery needs them. | Correlate requested, dispatched, completed/errored and acknowledged calls with stable IDs; never persist credentials or unrestricted raw tool payloads. |
| P2 | Add tool close/context-manager lifecycle only when a stateful tool is introduced. | Cleanup is tested after normal completion, exception, timeout and cancellation. |
| Future | Add remote event reconciliation only if the execution model becomes event-stream based. | Stream/history gap, seen-vs-answered distinction, idempotency and side-effect retry behavior are explicitly tested. |

## 6. Regression cases to carry into the implementation plan

1. Registry and schema integrity: every canonical name is unique; every provider schema is derived from its canonical input model; missing/extra adapter entries are detected.
2. Authorization: malformed input, unknown name, and unauthorized name are rejected before the handler runs; Runtime-created identity and grants cannot be overridden by model output.
3. Results: valid typed output round-trips; invalid output is rejected; expected tool errors and unexpected exceptions map to distinct bounded representations.
4. Async safety: blocking sync handlers do not block the event loop; async handlers are awaited; timeout and cancellation behavior is deterministic.
5. Loop ownership: fake and real provider adapters follow the same shared bounded loop; max-round exhaustion is enforced once, not independently per provider.
6. Middleware: Input/Wrap/Output ordering and exception behavior are deterministic; middleware cannot change Host-owned grants, approvals, or workflow state.
7. Evidence: if call events are added, duplicate delivery does not duplicate a completed local call; an unacknowledged external side effect is not blindly re-executed.
8. Lifecycle: if stateful tools are added, close runs exactly once across success, error, timeout and cancellation paths.
9. Builder separation: Builder has no canonical model-callable tool grant; changed-path detection, independent validation, and synchronization remain Runtime-owned.

## 7. Non-goals and anti-patterns

- Do not add a second Tool Capability Catalog, registry, dispatcher, or execution loop.
- Do not copy Anthropic's private `_toolsets` package or provider-specific Messages runner into Breakdown.
- Do not create a Browser/Computer family abstraction until Breakdown has a real stateful multi-member capability family.
- Do not treat the SDK's per-tool confirmation callback as equivalent to Breakdown's user approval of a frozen plan.
- Do not move workflow transitions, budget ownership, or approval authority into middleware or Agents.
- Do not infer that a filesystem path policy confines an unrestricted shell/subprocess.
- Do not introduce a remote session/reconciliation service for the current stateless CLI lifecycle.
- Do not implement the recommendations without a fresh source check, scoped implementation plan, and the required approval.

## 8. Source references

### Breakdown (commit `955050197725`)

- [Canonical tools and dispatch](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/breakdown/tools.py)
- [Role toolkit and role grants](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/breakdown/roles/__init__.py)
- [Live provider adapter and current tool loop](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/breakdown/live_backend.py)
- [Runtime/bootstrap and resource construction](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/breakdown/bootstrap.py)
- [Workflow progression](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/breakdown/engine.py)
- [Durable event store](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/breakdown/events.py)
- [Shared models and event/backend contracts](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/breakdown/models.py)
- [Tool tests](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/tests/test_tools.py)
- [Provider backend tests](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/tests/test_live_backend.py)
- [Event persistence tests](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/tests/test_events.py)
- [Current architecture and plan decisions](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/PLANS.md)
- [Current repository overview](https://github.com/itz1508/Breakdown/blob/95505019772544329fa9f9ab3d9148d232cf7b56/README.md)

### Anthropic Python SDK 2.13.0 (commit `bda18c620dbe`)

- [Shared dispatch helpers](https://github.com/anthropics/anthropic-sdk-python/blob/bda18c620dbec4c7febed947d7b8367d84c9171d/src/anthropic/lib/tools/_tool_dispatch.py)
- [Messages API tool runner](https://github.com/anthropics/anthropic-sdk-python/blob/bda18c620dbec4c7febed947d7b8367d84c9171d/src/anthropic/lib/tools/_beta_runner.py)
- [Managed-session event runner](https://github.com/anthropics/anthropic-sdk-python/blob/bda18c620dbec4c7febed947d7b8367d84c9171d/src/anthropic/lib/tools/_beta_session_runner.py)
- [Tool member/registry base](https://github.com/anthropics/anthropic-sdk-python/blob/bda18c620dbec4c7febed947d7b8367d84c9171d/src/anthropic/lib/tools/_toolsets/_base.py)
- [Browser member metadata and generated-schema drift guard](https://github.com/anthropics/anthropic-sdk-python/blob/bda18c620dbec4c7febed947d7b8367d84c9171d/src/anthropic/lib/tools/_toolsets/_registry.py)
- [Path and file policy](https://github.com/anthropics/anthropic-sdk-python/blob/bda18c620dbec4c7febed947d7b8367d84c9171d/src/anthropic/lib/tools/_toolsets/_security.py)
- [Function tools, Pydantic validation and ToolError](https://github.com/anthropics/anthropic-sdk-python/blob/bda18c620dbec4c7febed947d7b8367d84c9171d/src/anthropic/lib/tools/_beta_functions.py)
- [Agent tool context and file/shell factories](https://github.com/anthropics/anthropic-sdk-python/blob/bda18c620dbec4c7febed947d7b8367d84c9171d/src/anthropic/lib/tools/agent_toolset.py)
- [MCP adapter](https://github.com/anthropics/anthropic-sdk-python/blob/bda18c620dbec4c7febed947d7b8367d84c9171d/src/anthropic/lib/tools/mcp.py)

## Review limitations

This review inspected GitHub source files, the recursive repository tree, and relevant existing tests. It did not clone the repository, execute pytest/ruff/mypy, run a live model, or validate behavior against a running deployment. Coverage statuses are source-based findings, not test-run results or a security certification. Re-run the repository's normal checks after any implementation change.
