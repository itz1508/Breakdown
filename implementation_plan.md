# Implementation Plan — Phase 3a: Orchestration Economics + Live OpenAI-Compatible Backends

## Overview

**Goal:** Apply the orchestration patterns from the three Anthropic references
(plan-big/execute-small economics, multiagent orchestration, async delegation)
to complete the OneShot Breakdown engine — going live through OpenAI-compatible
APIs using a Databricks key or any custom API key, without the Anthropic-only
Managed Agents platform.

**Why rebuild rather than use the CMA SDK:** the reference architecture
(multiagent block, session threads, /v1/agents) is Anthropic-platform-specific
and requires the managed-agents-2026-04-01 beta. A Databricks Model Serving
endpoint or custom gateway exposes OpenAI-compatible chat completions — not
Managed Agents. Our engine already IS the orchestrator: contract-driven stages,
durable stores, budget enforcement, safety boundary, and approvals are the
rebuilt equivalents of CMA's session/thread/budget machinery. What remains
missing is (a) the live model adapter layer and (b) two pattern-derived
observability/economics upgrades: per-stage cost attribution (the cookbook's
"per-thread metering in production telemetry") and the per-role backend seam
(the cookbook's two-model team: frontier judgment vs. cheap token-heavy reading).

**Scope:** one cycle ("Phase 3a") delivering: offline foundation upgrades
(stage-level cost attribution, per-role backend selection),
OpenAICompatibleRoleBackend with structured outputs + canonical tool loop,
OpenAICompatibleCodingBackend (sandbox-confined file authoring), --live CLI
path gated by validated bindings, evals --live mode producing real binding
evidence, a live-probe script, and docs (Databricks + custom-key recipes).
All tested offline against a mock HTTP transport; live verification is opt-in
requiring a real key.

**Explicitly deferred (Phase 3b):** parallel worker fan-out (def-1 declares
execution_order: sequential), streaming/resume/hooks capabilities, Anthropic
CMA interop.

## Pattern mapping learned from the sources

| Reference pattern | Our equivalent |
|---|---|
| Frontier orchestrator + cheap workers | Per-role model tiers via env (BREAKDOWN_MODEL_AUDITOR frontier, BREAKDOWN_MODEL_RESEARCHER cheap) through the per-role backend seam |
| Per-thread cumulative usage / cost attribution | RunRecord.stage_usage + CostSummary.by_stage + STAGE_COMPLETED event payload |
| Session budget as fan-out guardrail | Existing cost_budget (max_tokens/max_tool_calls/completion_reserve) — now attributed per stage |
| Delegation visible in event stream | Existing stage/artifact events + per-stage usage in payloads |
| Advisor consultation | Already implemented: auditor's bounded coder sub-role |
| Hub peer-messaging | Rejected by design — handoff_rules: roles never invoke roles; runtime owns progression |
| Delegation floor cost / brief-granularity optimum | Documented guidance for future def-2 parallelism + adapter tool-round cap |
| "Verify the decomposition, not just the facts" | Documented as candidate future eval zero (not built this cycle) |

## Types

**breakdown/models.py:**
- RunRecord: add `stage_usage: Mapping[str, CostSummary]` (default {}) —
  cumulative per-stage tokens/calls; retries add to the stage. Defaulted field
  keeps stored runs compatible.
- CostSummary: add `by_stage: Mapping[str, CostSummary]` (default {}) —
  completion-time breakdown projection (leaves carry empty by_stage).
- Settings: add live-API fields (env prefix BREAKDOWN_):
  - api_base_url: str | None
  - api_key: SecretStr | None (never repr-logged, never persisted)
  - model: str | None (default model for all roles)
  - model_auditor / model_researcher / model_coder / model_planner: str | None
    (per-role tier overrides; fall back to model)
  - api_max_tool_rounds: int = 8 (tool-loop bound)

**breakdown/live_backend.py (new):**
- LiveBackendError(RuntimeError) — adapter failures (auth, network, malformed
  response, tool-round exhaustion).
- Implements existing RoleBackend / CodingBackend protocols; no new protocols.

**Bindings sample shape (no model change):** BackendBinding with
implementation "openai_compatible", package_name "openai",
required_capabilities [structured_output, tool_calls, tool_loop, usage_data],
live_required true.

## Files

**New:** breakdown/live_backend.py · tests/test_live_backend.py ·
tests/test_stage_usage.py · scripts/live_probe.py · bindings.example.json ·
implementation_plan.md (this document).

**Modified:**
- breakdown/models.py — RunRecord.stage_usage, CostSummary.by_stage, Settings.
- breakdown/engine.py — accumulate stage_usage on every commit path;
  STAGE_COMPLETED payload gains tokens/tool_calls; budget_exhausted_record
  gains stage_usage snapshot.
- breakdown/completion.py — build_completion_record projects by_stage.
- breakdown/reports.py — deterministic "## Stage cost" table.
- breakdown/bootstrap.py — build_runtime gains role_backends mapping seam;
  build_live_backends(settings); bindings coverage check (data-driven from the
  definition's ROLE stages: each role's binding permitted_operations must cover
  its stage operations).
- breakdown/__main__.py — --live flag; live construction path with named-env
  errors; mutual exclusion with --offline-demo.
- evals/run.py — --live mode (role cases via live backends from env; safety
  cases stay scripted — they test the boundary, not the model).
- .env.example — BREAKDOWN_API_* names + Databricks/custom-gateway recipes.
- README.md — live quickstart, two-tier economics note, bindings-gate flow.
- PLANS.md — Phase 3a entry + decisions D30–D34.
- pyproject.toml / uv.lock — via `uv add "openai>=1.50,<3"`.

**Deleted/moved:** none.


## Functions

**New (breakdown/live_backend.py):**
- `build_openai_client(settings) -> AsyncOpenAI` — base_url + api_key from
  settings; LiveBackendError naming the exact env vars when unset.
- `tool_schemas(tool_names) -> list[dict]` — OpenAI function-tool definitions
  from the TOOLS registry (name, description, input_model.model_json_schema()).
- `OpenAICompatibleRoleBackend.generate(request)` — async loop: chat completion
  with tools; dispatch tool calls via dispatch_tool after verifying the name is
  in request.tool_names; append results; bounded by max_tool_rounds; final
  structured pass with response_format json_schema (strict=True), falling back
  to prompt-JSON parsing if the endpoint rejects it; usage mapping
  prompt_tokens/completion_tokens -> TokenUsage, tool_calls = dispatched count.
- `OpenAICompatibleCodingBackend.apply_task(request)` — prompt carries task +
  current contents of target paths read from the sandbox; model returns JSON
  {path: new_content}; adapter writes ONLY paths in task.target_paths inside
  the sandbox; COMPLETED/FAILED result with usage.
- `bootstrap.build_live_backends(settings)` — resolves per-role model
  (model_<role> override -> model), shared client, tool_root = target repo.
- `engine._add_stage_usage(stage_usage, stage_id, usage)` — pure accumulation.
- `scripts/live_probe.py:main()` — env-gated live smoke: one structured-output
  request + one tool round; prints model/latency/usage; nonzero exit on failure.

**Modified:**
- engine._run_role_stage — accumulate stage_usage into every update_run commit
  path (success, failure, retry, loopback, budget); STAGE_COMPLETED payload.
- engine._route_budget_exhausted — budget record gains stage_usage snapshot.
- engine._complete_run — passes stage_usage to build_completion_record.
- completion.build_completion_record — stage_usage kwarg -> cost_summary.by_stage.
- reports.render_run_report — "## Stage cost" section.
- bootstrap.build_runtime — role_backends seam; bindings coverage check.
- __main__._build_runtime — --live branch.
- evals/run.py:main — --live mode.

## Classes

**New:** OpenAICompatibleRoleBackend (client, model, tool_root,
max_tool_rounds; methods generate/_dispatch_tool_call/_structured_final) ·
OpenAICompatibleCodingBackend (client, model; method apply_task). Both in
breakdown/live_backend.py, implementing existing protocols, no inheritance.

**Modified:** RunRecord, CostSummary, Settings (field additions).

## Dependencies

- Add `openai>=1.50,<3` via `uv add` (authorized; updates uv.lock). Used as an
  OpenAI-compatible HTTP client: Databricks Model Serving
  (base_url=https://<workspace>/serving-endpoints/<endpoint>/v1, api_key=PAT),
  custom gateways (LiteLLM/vLLM/Ollama-style), or OpenAI directly.

## Testing

- tests/test_stage_usage.py (~5 rows): happy-path totals == sum(by_stage);
  retry accumulation; budget record snapshot; STAGE_COMPLETED payload; report
  table determinism.
- tests/test_live_backend.py (~8 rows, AsyncOpenAI over httpx.MockTransport):
  request mapping + usage; tool loop through real dispatch_tool on a fixture
  repo; tool-name enforcement; round exhaustion; json_schema 400 fallback;
  malformed output rejection; coding backend sandbox confinement (overreaching
  path -> FAILED, not written); secret hygiene (key absent from errors/reprs).
- tests/test_cli_runtime.py additions: --live missing-settings error names env
  vars; --live + --offline-demo mutually exclusive; per-role seam routing;
  missing role backend -> BootstrapError; bindings coverage violation.
- Existing suites: unchanged assertions (stage-cost additions touch only new
  fields/payloads).
- Validation: full offline gate; live validation opt-in via scripts/live_probe.py
  and evals --live with the user's key, feeding BackendBinding records.

## Implementation Order

1. Save this document (done).
2. uv add "openai>=1.50,<3"; uv sync --locked.
3. models.py: stage_usage, by_stage, Settings live fields.
4. Engine attribution (all commit paths + event payload + budget snapshot).
5. completion.py + reports.py projections.
6. tests/test_stage_usage.py -> green.
7. bootstrap per-role seam + bindings coverage; seam tests.
8. live_backend.py (client factory, tool schemas, role + coding backends).
9. tests/test_live_backend.py -> green.
10. CLI --live wiring + error tests; .env.example; bindings.example.json.
11. evals --live mode + scripts/live_probe.py.
12. Docs: README live quickstart; PLANS.md Phase 3a + D30–D34.
13. Full gate -> single commit.
14. Hand back: live-probe instructions (Databricks PAT or custom key) and the
    evals->binding flow.

## Gap review (pre-execution; all fixes folded into this plan)

- G1 Bindings coverage is data-driven: derived from the definition's ROLE
  stages (owner -> stage operations), not a hard-coded role map.
- G2 evals --live keeps scoreboard semantics; documented as binding-evidence
  collection (live acceptance depends on the model).
- G3 Coder sub-role included in the per-role seam (role_factory resolves it
  like any role; falls back to the shared backend).
- G4 CLI --live REQUIRES a validated bindings file (D33). Bootstrap order:
  evals --live (drives roles directly, no bindings needed) -> binding record
  -> CLI --live. Missing bindings -> BootstrapError explaining the flow.
- G5 SecretStr hygiene: error messages reference env var names only; a test
  asserts the key value never appears in raised errors.
- G6 json_schema strict mode is provider-dependent: adapter tries
  response_format json_schema (strict=True) and falls back to prompt-JSON on
  endpoint rejection (400) — pydantic validation remains the authority.
- G7 openai SDK pin `<3` guards against unverified major-version drift;
  code targets the stable chat.completions surface only.
- G8 CostSummary self-reference (by_stage) is safe under pydantic forward-ref
  resolution (same pattern already proven by StageResult.usage).

- Tests use httpx.MockTransport (transitive via openai) — no new dev dep.
