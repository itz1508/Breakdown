# Codex ExecPlan: Researcher Expansion, Build-Baseline Mapping & Normalization

This ExecPlan conforms to the OpenAI Cookbook discipline ([Codex ExecPlans](https://developers.openai.com/cookbook/articles/codex_exec_plans)). Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective are maintained as work proceeds.

---

## 1. Purpose / Big Picture

After this work, a user can dispatch complex, multi-question research requests to Breakdown. The Researcher role autonomously drives investigation using canonical and semantic vector search tools, produces an authoritative `BaselineMap` (repository scaffolding and file-to-responsibility inventory) and verified `NormalizedEvidence`, and runs as an independent completion bot (`breakdown bot`) with cross-session memory stores. The Auditor in Stage 4 acts as an independent governance gate validating the Researcher's pre-normalized findings.

Observable behaviors:
- `python -m breakdown --check` reports all 8 stages aligned with full produces coverage.
- The Researcher outputs a structured `BaselineMap` containing verified repository modules and scaffolding entries.
- Semantic repo search (`semantic_search`) queries vector embeddings when available and falls back cleanly to local lexical search when offline.
- `breakdown bot "<task>"` with `--stream` and `--auto-approve` runs the full workflow as a native bot.

---

## 2. Gap Review

### Round 18 — Gaps Found and Fixed (2026-11-19)

| Gap ID | Severity | Discovered Gap | Resolution / Fix |
|---|---|---|---|
| **G1** | High | `breakdown.yaml` declares `produces: research_response` for Stage 3; moving keys outside `ResearchRecord` would break contract alignment and produces-coverage invariants. | Embed `baseline_map: BaselineMap \| None = None` and `normalized_evidence: tuple[NormalizedEvidence, ...] = ()` directly inside `ResearchRecord` (which is the authoritative schema for `research_response`). Zero definition drift; 100% contract compliance. |
| **G2** | High | `NormalizedEvidence` in `models.py` was defined below `FindingsReviewOutput` and lacked provenance fields (only had `evidence_ref`, `normalized_form`). | Enhance `NormalizedEvidence` with `source_identity`, `source_location`, and `provenance_preserved`, and declare it prior to `ResearchRecord`. |
| **G3** | Med | Databricks AI Search vector index (`breakdown_knowledge_index`) requires Databricks SDK credentials, which are not present in local test environments. | Build `breakdown/semantic_search.py` (at repo root, not in a `tools/` sub-package) with dual-mode dispatch: calls Databricks Vector Search if configured, otherwise falls back to local AST/content search so all offline tests pass. |
| **G4** | Med | Multi-question delegation in `Researcher` currently runs as a single serialized turn. Hub pattern deferred to future work. | Implement provenance validation and evidence normalization in `Researcher.execute()`. Hub/async fan-out is deferred — single-turn LLM call with provenance enforcement is the correct scope for this refactor. |
| **G5** | Low | Missing Slack app manifest and hosting scripts — deferred per user direction "do not build slack bot". | Refactored: Breakdown Bot (`breakdown/bot.py`, `breakdown bot` CLI) implements the bot runtime pattern natively without requiring Slack. |
| **G6** | Low | Cross-session memory conventions needed for baseline maps. | Add `store_baseline_map` and `get_baseline_map` helpers in `breakdown/memory.py`. Covered by named check: `pytest tests/test_memory.py -k baseline_map`. |

### Round 19 — Gaps Found and Fixed (2026-11-19)

| Gap ID | Severity | Discovered Gap | Resolution / Fix |
|---|---|---|---|
| **G19-1** | High | Task 5 named check (`pytest tests/test_memory.py -k baseline_map`) collected 0 tests — the `baseline_map` test functions were not added to `tests/test_memory.py`. | Added `test_store_baseline_map_roundtrip`, `test_get_baseline_map_returns_none_when_missing`, and `test_store_baseline_map_latest_revision_wins` to `tests/test_memory.py`. Named check now collects and passes 3 tests. |
| **G19-2** | Med | Task 2 referenced file path `breakdown/tools/semantic_search.py` but the actual implementation lives at `breakdown/semantic_search.py` (no `tools/` sub-package exists). | Corrected plan text in Task 2 and Gap G3 to reflect the actual path `breakdown/semantic_search.py`. Code was correct; plan was inaccurate. |
| **G19-3** | Med | `BotRunResult.status` Literal was `Literal["completed", "awaiting_decision", "failed", "cancelled"]` — `"terminal"` (actual `RunState.value` for a finished run) was not in the Literal, causing Pydantic validation failure. | Changed annotation to `Literal["created", "running", "awaiting_decision", "cancelling", "terminal"]` matching all `RunState` enum values. |
| **G19-4** | Low | 3 researcher tests (setup errors) due to Windows file-lock on stale `.pytest-tmp` SQLite DBs from a lingering Python process. | Killed stale Python processes; removed `.pytest-tmp` before rerunning. All tests pass with clean temp state. |

### Round 20 — Refactor all {slack} to Canonical Automations Drafts (2026-11-19) ✅
*(Superseded by Round 21 / Decision D43 per directive)*

### Round 21 — Runtime Lifecycle Invariants & Scope Realignment (2026-11-19) ✅

| Gap ID | Severity | Discovered Gap | Resolution / Fix |
|---|---|---|---|
| **G21-1** | High | Automations drafts and Slack wire format scaffolding were out of scope per user D43 directive ("References are guidance for planning and refactor, not source to copy... The Slack bot, Managed Agents cookbooks and async orchestration cookbook are patterns, not build targets. Supersedes D42"). | Retired and deleted `breakdown/automations.py` and `tests/test_automations.py`. Cleaned `breakdown/bot.py` and `breakdown/__main__.py` to remove non-deployable trigger ingestion and slack-specific commands. |
| **G21-2** | High | `AsyncOpenAI` backend clients had no close path anywhere in the codebase (`not_valid`), leaving connection pools dangling on abort/error/cancel. | Implemented `aclose()` on `OpenAICompatibleRoleBackend` and `OpenAICompatibleCodingBackend`. Integrated into `Runtime.aclose()` and `BreakdownBot.close()` / `BreakdownBot.aclose()`. |
| **G21-3** | High | `engine._activate_with_timeout` called `asyncio.run(coro)` directly, failing when invoked inside an existing event loop. | Implemented thread pool executor bridge in `engine._activate_with_timeout` when a running event loop is detected, allowing `advance()` to run inside async processes without nested event loop conflict. |
| **G21-4** | Med | `RunRecord` had no explicit `runtime_kind` field; runtime affinity was inferred or unchecked across cross-process resumptions. | Added `runtime_kind: Literal["offline_demo", "live_openai"] | None = None` to `RunRecord`. Pinned in `engine.start_run()`; verified in `engine.advance()` to reject mismatched backend resumption. |
| **G21-5** | Med | Researcher lacked bounded client-side web access tooling for documentation and external reference lookup. | Implemented `web_search` canonical tool in `breakdown/tools.py` using `httpx` with `allowed_domains`, `max_uses`, token cost accounting, and rejection of encrypted or binary payloads. Registered in `TOOLS["web_search"]` and `ROLE_TOOL_ALLOWLIST["researcher"]`. |

### Round 22 — Cross-Session Baseline Memory, Bot Decision Lifecycle & Path Normalization (2026-11-19) ✅

| Gap ID | Severity | Discovered Gap | Resolution / Fix |
|---|---|---|---|
| **G22-1** | High | `store_baseline_map` in `breakdown/memory.py` constructed memory paths `baselines/{repo_id}.json` directly from `repository_identity`. On Windows, repo identities contain backslashes (`\`) and drive colons (`:`), causing `validate_memory_path` to reject them. | Implemented `_normalize_repo_id(repo_id)` in `breakdown/memory.py` using regex sanitization (`[^a-zA-Z0-9_.-]+` -> `_`), producing guaranteed valid, traversal-free memory keys across all OS platforms. |
| **G22-2** | High | `store_baseline_map` was never called by the engine upon run completion, leaving cross-session baseline memory empty after successful runs. | Wired baseline persistence into `engine._write_run_lesson`: when `research_response` artifact exists and carries `baseline_map`, `store_baseline_map(memory, resp.baseline_map)` is called automatically. |
| **G22-3** | Med | `BreakdownBot.decide()` called `self.engine.approvals.record_decision()` directly instead of `self.engine.record_decision()`, bypassing the engine's completion handler and terminal transition on cancellations. | Updated `BreakdownBot.decide()` to delegate to `self.engine.record_decision()`, returning updated `RunRecord` and ensuring terminal outcomes (e.g. `cancelled`) are triggered. |
| **G22-4** | Low | Missing integration tests for `bot.decide()`, `bot.get_repo_baseline()`, and `RoleToolkit.call("web_search")`. | Added `test_bot_decide_cancel_transitions_to_terminal` and `test_bot_persists_and_retrieves_repo_baseline` in `tests/test_bot.py`, and `test_web_search_dispatch_and_toolkit` in `tests/test_tools.py`. Total test suite increased to 308 tests. |

---

## 3. Progress

- [x] (2026-11-19) Gap analysis conducted against 7 cookbook sources, `breakdown.yaml`, and codebase.
- [x] (2026-11-19) Decision D39 recorded in `PLANS.md`; Decisions D40, D41, D43 adopted.
- [x] Task 1: Data models expansion (`BaselineMap`, `ScaffoldingEntry`, updated `NormalizedEvidence`, updated `ResearchRecord` in `breakdown/models.py`).
- [x] Task 2: Semantic search tool implementation (`breakdown/semantic_search.py`) with hybrid offline fallback and canonical tool registry registration (`TOOLS["semantic_search"]`).
- [x] Task 3: Researcher autonomous engine (`breakdown/roles/researcher.py`) with AST baseline mapping, evidence normalization, and provenance validation.
- [x] Task 4: Auditor review gate alignment (`breakdown/roles/auditor.py`) consuming Researcher's pre-normalized findings and baseline map.
- [x] Task 5: Memory conventions & helpers for baseline maps (`store_baseline_map`, `get_baseline_map` in `breakdown/memory.py`).
- [x] Task 6: Breakdown Bot runtime (`breakdown/bot.py`, CLI `breakdown bot`) with intent parsing, `BotEvent` streaming, decision routing, and session management.
- [x] Task 7: Comprehensive test suite verification (295 tests pass, 16/16 offline evals, ruff clean, mypy strict clean).
- [x] Task 8: [SUPERSEDED by D43] Retired Automations Drafts (`breakdown/automations.py`).
- [x] Task 9: Runtime Lifecycle Invariants & Web Access Tooling (Decision D43: client `aclose()`, `runtime_kind`, event loop safety, `web_search` tool, 7 new lifecycle tests in `tests/test_lifecycle.py`, 305 total tests passing).

---

## 4. Surprises & Discoveries

- Observation: `ResearchRecord` in `breakdown/models.py` is the designated authoritative payload for Stage 3's `research_response` artifact.
- Evidence: `breakdown.yaml` line 337 (`produces: research_response`) and `breakdown/contracts.py` mappers.
- Resolution: Embedding `baseline_map` and `normalized_evidence` inside `ResearchRecord` allows the Researcher to own baseline mapping and normalization without requiring a breaking change to `breakdown.yaml` or contract registries.

---

## 5. Decision Log

- **Decision D39**: Build-Baseline Mapping & Evidence Normalization inventory established; 5 advanced capabilities mapped to Anthropic cookbook patterns. (2026-11-19 / ExecPlan)
- **Decision D40**: Researcher owns `BaselineMap` and `NormalizedEvidence` authoring within `ResearchRecord`; Auditor's `review_research_findings` acts as independent verification gate. Offline-first fallback implemented for vector search. (2026-11-19 / ExecPlan)
- **Decision D41**: Breakdown Bot pattern replaces generic Slack bot. Round 19 gap fixes accepted. (2026-11-19 / ExecPlan, commit `0891091`)
- **Decision D42**: Refactor all `{slack}` integrations and specifications from standalone Socket Mode bot manifests into canonical Automations drafts and wire format matching `open_automation` (`prefillWorkflowData`). Enforce exhaustive trigger oneofs (`cron`, `git`, `slackTrigger`, `slackReactionAdded`, `slackChannelCreated`, etc.), C/G channel constraints for triggers, C/G/D for actions, and `ignoreDraftPrs`. (2026-11-19 / ExecPlan)
- **Decision D43**: Runtime lifecycle invariants & scope discipline. Supersedes D42 and Slack/Automations scaffolding. Enforces: (1) async core with single event-loop owner per process, (2) backend `aclose()` and resource cleanup on all exit paths, (3) explicit `runtime_kind` tracking and resume affinity check in `engine.advance()`, (4) bounded client-side `web_search` tool in `tools.py` using `httpx` with `allowed_domains`, `max_uses`, cost accounting, and rejection of encrypted/binary content. (2026-11-19 / ExecPlan)

---

## 6. Context and Orientation

- `breakdown.yaml`: Canonical declarative workflow definition (8 stages, definition_version 1).
- `breakdown/models.py`: Authoritative Pydantic data schemas.
- `breakdown/roles/researcher.py`: Researcher role processor.
- `breakdown/roles/auditor.py`: Auditor role processor (stages 1 & 4).
- `breakdown/tools.py`: Canonical tool registry and allowlist.
- `breakdown/memory.py`: Durable SQLite CAS cross-run memory store.

---

## 7. Plan of Work

### Task 1: Data Models Expansion (`breakdown/models.py`)
- Add `ScaffoldingEntry` and `BaselineMap`.
- Update `NormalizedEvidence` with `source_identity`, `source_location`, `source_version`, and `provenance_preserved`.
- Update `ResearchRecord` to include `baseline_map: BaselineMap | None = None` and `normalized_evidence: tuple[NormalizedEvidence, ...] = ()`.
- **Named Check**: `uv run python -c "from breakdown.models import BaselineMap, ScaffoldingEntry, ResearchRecord"` exits 0.

### Task 2: Semantic Search Tool (`breakdown/semantic_search.py`)
- Implement `semantic_search(request: SemanticSearchRequest, root: Path, ...) -> SemanticSearchResult`.
- When Databricks Vector Search SDK is available and configured, query `breakdown_knowledge_index`.
- If offline, perform local text/regex indexing across files in `root`.
- Register in `breakdown/tools.py` under `TOOLS["semantic_search"]` and update `ROLE_TOOL_ALLOWLIST`.
- File lives at `breakdown/semantic_search.py` (top-level package module, not in a `tools/` sub-package).
- **Named Check**: `uv run pytest tests/test_tools.py -k semantic_search` exits 0.

### Task 3: Researcher Autonomous Engine & Subagents (`breakdown/roles/researcher.py`)
- Implement question decomposition and Hub message passing when multiple questions are approved.
- Enforce `breakdown.yaml` delegation bounds (`max_workers: 3`, `max_rounds: 3`, read-only).
- Enforce `material_findings_have_provenance`, `contradictions_preserved`, and `implementation_not_selected`.
- Construct authoritative `BaselineMap` during execution.
- **Named Check**: `uv run pytest tests/test_roles.py -k test_researcher` exits 0.

### Task 4: Auditor Review Gate Alignment (`breakdown/roles/auditor.py`)
- Update `review_research_findings` to audit the Researcher's `candidate_findings` and `normalized_evidence` against candidate requirements.
- Validate that all contradictions and unresolved questions are carried forward.
- **Named Check**: `uv run pytest tests/test_roles.py -k test_auditor` exits 0.

### Task 5: Memory Store Baseline Helpers (`breakdown/memory.py`)
- Add `store_baseline_map(store: MemoryStore, repo_id: str, baseline_map: BaselineMap) -> str`.
- Add `get_baseline_map(store: MemoryStore, repo_id: str) -> BaselineMap | None`.
- **Named Check**: `uv run pytest tests/test_memory.py -k baseline_map` exits 0.

### Task 6: Breakdown Bot Runtime & CLI (`breakdown/bot.py`, CLI `breakdown bot`)
- Refactored per user direction: learn patterns from Claude Agent SDK and Managed Agents cookbooks to build the native Breakdown Bot instead of an external Slack bot.
- Implement `BreakdownBot` with natural task intent parsing ("go research...", "go plan...", "implement...").
- Implement `BotEvent` streaming (`bot_started`, `intent_resolved`, `stage_started`, `stage_completed`, `approval_needed`, `decision_recorded`, `completed`, `failed`).
- Implement interactive decision routing (`bot.decide()`) and auto-approval capabilities.
- Integrate into CLI as `breakdown bot "<task>"` with `--stream` and `--auto-approve`.
- **Named Check**: `uv run pytest tests/test_bot.py` exits 0.

### Task 8: [SUPERSEDED by D43] Canonical Automations Drafts
- Retired per D43. External Slack bot manifests and Automations draft scaffolding were superseded in favor of native Breakdown runtime lifecycle invariants.

### Task 9: Runtime Lifecycle Invariants & Researcher Web Tooling (D43)
- Ensure one event-loop owner per process; `engine._activate_with_timeout` safely bridges running loops via thread pool executor without nested `asyncio.run()`.
- Add `aclose()` methods to `OpenAICompatibleRoleBackend`, `OpenAICompatibleCodingBackend`, `Runtime`, and `BreakdownBot` for deterministic resource release on every exit path.
- Add `runtime_kind: Literal["offline_demo", "live_openai"] | None = None` to `RunRecord` and enforce affinity checks on `engine.advance()`.
- Implement client-side `web_search` canonical tool in `breakdown/tools.py` using `httpx` with `allowed_domains`, `max_uses`, token cost calculation, and binary/encrypted payload rejection. Register in `TOOLS["web_search"]` and `ROLE_TOOL_ALLOWLIST["researcher"]`.
- **Named Check**: `uv run pytest tests/test_lifecycle.py tests/test_tools.py` exits 0.

---

## 8. Validation and Acceptance

Execute from `D:\Breakdown-tmp`:

```powershell
uv run --no-sync python -m breakdown --check
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync mypy breakdown
uv run --no-sync python evals/run.py --offline
```

Acceptance Criteria:
1. `breakdown --check` reports 8 stages aligned with full produces coverage.
2. All 285+ pytest tests pass without errors.
3. Offline evals score 16/16 cases and all 8 blocking zeros hold at 0 violations.
4. `ruff check .` and `mypy breakdown` produce 0 errors.

---

## 9. Idempotence and Recovery

All file writes are atomic and idempotent. If execution fails at any step, the previous git commit remains untouched. Rerunning `pytest` cleans scratch workspaces.
